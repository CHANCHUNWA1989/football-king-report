"""Read-only exact fixture/score corroboration; no forecast or market promotion."""
import argparse
import json
from collections import defaultdict, Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from .source_publish_guard import verify, time
    from .team_identity import team_id
except ImportError:
    from source_publish_guard import verify, time
    from team_identity import team_id

# Explicit full club names observed in the published two-provider sample.
# Scoped to this result diagnostic, not the frozen prediction identity rules.
ALIASES = {
    ("laliga", "levanteud"): "levante",
    ("laliga", "realracingclubdesantander"): "racingdesantander",
    ("seriea", "bolognafc1909"): "bologna",
}
PUBLISHERS = {"thesportsdb", "football_data_org"}

def identity(league, name):
    value = team_id(league, name)
    return ALIASES.get((league, value), value)

def audit(report, now):
    stamp = verify(report, now=now)
    if not timedelta(0) <= now - stamp <= timedelta(hours=48):
        raise ValueError("STALE_OR_FUTURE_SOURCE")
    started = time(report["started_utc"])
    active = {p["provider"] for p in report["providers"]
              if p["configured"] and p["status"] in ("PARTIAL", "PARTIAL_COVERAGE")}
    votes = defaultdict(lambda: defaultdict(set))
    ids = defaultdict(set)
    rejected = Counter()
    for row in report["sampled_fixtures"]:
        provider = row["provider"]
        if provider not in PUBLISHERS or provider not in active:
            continue
        league = row["league"]
        h, a = identity(league, row["home"]), identity(league, row["away"])
        if not h or not a or h == a:
            rejected["INVALID_IDENTITY"] += 1
            continue
        kickoff = time(row["kickoff_utc"])
        key = (league, h, a, kickoff)
        native = row["provider_event_id"]
        ids[(provider, league, native)].add(key)
        if row["status"] != "FINISHED" or row["score_ft"] is None:
            continue
        if started < kickoff + timedelta(hours=2):
            rejected["NOT_POST_MATCH"] += 1
            continue
        votes[key][provider].add((native, tuple(row["score_ft"])))
    conflicts = {k for keys in ids.values() if len(keys) > 1 for k in keys}
    rows = []
    for key, providers in sorted(votes.items()):
        if key in conflicts:
            rejected["NATIVE_ID_CONFLICT"] += 1
            continue
        if set(providers) != PUBLISHERS:
            rejected["MISSING_SECOND_PUBLISHER"] += 1
            continue
        if any(len(v) != 1 for v in providers.values()):
            rejected["AMBIGUOUS_PROVIDER_OBSERVATION"] += 1
            continue
        evidence = {p: next(iter(v)) for p, v in providers.items()}
        if len({s for _, s in evidence.values()}) != 1:
            rejected["CONFLICTING_SCORE"] += 1
            continue
        league, h, a, kickoff = key
        rows.append({"league": league, "home_id": h, "away_id": a,
                     "kickoff_utc": kickoff.isoformat(),
                     "score_ft": list(next(iter(evidence.values()))[1]),
                     "provider_event_ids": {p: v[0] for p, v in sorted(evidence.items())},
                     "independently_authenticated": False})
    return {"schema": "football-king-score-corroboration-v1", "status": "HOLD",
            "source_collected_utc": stamp.isoformat(), "as_of_utc": now.isoformat(),
            "two_publisher_score_candidates": len(rows), "rows": rows,
            "rejected": dict(rejected), "authenticated_forward_samples": 0,
            "independent_oos_verified": False, "positive_ev_verified": False,
            "production_recommendations": "DISABLED"}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    source = Path(args.source)
    if source.stat().st_size > 500000:
        raise ValueError("SOURCE_TOO_LARGE")
    report = audit(json.loads(source.read_text(encoding="utf-8")), datetime.now(timezone.utc))
    Path(args.output).write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")

if __name__ == "__main__":
    main()
