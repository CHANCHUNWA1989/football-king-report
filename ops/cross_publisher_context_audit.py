"""Compare archived secondary publishers to gateway context, never admit fixtures."""
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
try:
    from .fixture_source_evidence import verify_for_artifact, digest, utc
    from .source_publish_guard import verify
    from .team_identity import team_id
except ImportError:
    from fixture_source_evidence import verify_for_artifact, digest, utc
    from source_publish_guard import verify
    from team_identity import team_id

HK = ZoneInfo("Asia/Hong_Kong")


def pair(league, row):
    return (team_id(league, row.get("home")), team_id(league, row.get("away")))


def audit(doc, secondary):
    verify_for_artifact(doc)
    if doc.get("clock_problem") is not None:
        raise ValueError("GATEWAY_CLOCK_HOLD")
    cutoff = utc(doc["completed_utc"])
    collected = verify(secondary, now=cutoff)
    if secondary.get("status") != "RESEARCH_ONLY" or not timedelta(0) <= cutoff-collected <= timedelta(hours=16):
        raise ValueError("SECONDARY_CLOCK_OR_STATUS")
    active = {p["provider"] for p in secondary["providers"]
              if p["configured"] is True and p["status"] in ("PARTIAL", "PARTIAL_COVERAGE")
              and p["sampled_fixture_count"] > 0}
    results = []
    counts = Counter()
    for batch in doc["batches"]:
        league = batch["requested_league"]
        if (batch.get("source_context_complete") is not True or batch.get("rejected")
                or collected > utc(batch["observed_utc"])):
            counts["BATCH_CONTEXT_HOLD"] += 1
            continue
        groups = defaultdict(list)
        for r in secondary["sampled_fixtures"]:
            if r["league"] != league or r["provider"] not in active:
                continue
            k = pair(league, r)
            if not all(k) or k[0] == k[1]:
                continue
            ko = utc(r["kickoff_utc"])
            if not cutoff+timedelta(minutes=60) <= ko <= cutoff+timedelta(days=7):
                continue
            groups[k].append(r)
        for key, rows in sorted(groups.items()):
            votes = Counter(r["provider"] for r in rows)
            clocks = {utc(r["kickoff_utc"]) for r in rows}
            label = None
            candidates = []
            adjacent = []
            if any(r["status"] != "SCHEDULED" or r["score_ft"] is not None for r in rows):
                label = "SECONDARY_STATUS_CONFLICT"
            elif any(v != 1 for v in votes.values()):
                label = "DUPLICATE_PROVIDER_VOTE"
            elif len(votes) < 2:
                label = "SINGLE_PROVIDER"
            elif len(clocks) != 1:
                label = "SECONDARY_UTC_CONFLICT"
            else:
                ko = next(iter(clocks))
                days = {ko.date().isoformat(), ko.astimezone(HK).date().isoformat()}
                same_day = [r for r in batch["rows"] if r["date"] in days]
                candidates = [r for r in same_day if pair(league,r) == key]
                conflict = any(pair(league,r) != key and set(pair(league,r)).intersection(key)
                               and r["status"] in ("SCHEDULED","UNCONFIRMED") for r in same_day)
                if conflict:
                    label = "GATEWAY_OPPONENT_OR_DIRECTION_CONFLICT"
                elif len(candidates) > 1:
                    label = "GATEWAY_AMBIGUOUS"
                elif not candidates:
                    # Adjacent calendar days are diagnostic only: never adjust
                    # the gateway date or authorize a repaired fixture here.
                    nearby_days = {(date.fromisoformat(day)+timedelta(days=offset)).isoformat()
                                   for day in days for offset in (-1, 1)} - days
                    adjacent = [r for r in batch["rows"]
                                if r["date"] in nearby_days and pair(league,r) == key]
                    if len(adjacent) > 1:
                        label = "ADJACENT_DATE_AMBIGUOUS_HOLD"
                    elif adjacent:
                        label = "ADJACENT_DATE_CONFLICT_HOLD"
                    else:
                        label = "NO_MATCH_IN_CAPTURED_PROJECTION"
                elif candidates[0]["status"] not in ("SCHEDULED","UNCONFIRMED"):
                    label = "GATEWAY_STATUS_CONFLICT"
                elif candidates[0]["kickoff_utc"] is None:
                    label = "DATE_ONLY_CONTEXT_MATCH"
                else:
                    try:
                        label = ("EXACT_UTC_CONTEXT_MATCH" if utc(candidates[0]["kickoff_utc"]) == ko
                                 else "GATEWAY_UTC_CONFLICT")
                    except (ValueError, TypeError, OverflowError):
                        label = "GATEWAY_UTC_CONFLICT"
            counts[label] += 1
            results.append({"requested_league":league,"home_key":key[0],"away_key":key[1],
                            "publisher_count":len(votes),"publisher_ids":sorted(
                                [[r["provider"],r["provider_event_id"]] for r in rows]),
                            "recorded_utc":sorted(t.isoformat() for t in clocks),
                            "gateway_candidate_count":len(candidates),
                            "adjacent_date_candidate_count":len(adjacent),
                            "adjacent_gateway_dates":sorted({r["date"] for r in adjacent}),
                            "classification":label})
    return {"schema":"football-king-cross-publisher-context-audit-v1",
            "gateway_batches_sha256":doc["batches_sha256"],
            "secondary_document_sha256":digest(secondary),"counts":dict(sorted(counts.items())),
            "groups":results,"publisher_independence_authenticated":False,
            "native_identity_authenticated":False,"missing_gateway_fixtures_proven":False,
            "admitted_new_fixtures":0,"production_recommendations":"DISABLED","status":"HOLD"}


def load(path):
    with Path(path).open("rb") as f:
        raw=f.read(8_000_001)
    if not 0<len(raw)<=8_000_000:
        raise ValueError("INPUT_SIZE")
    def unique(pairs):
        out={}
        for k,v in pairs:
            if k in out:
                raise ValueError("DUPLICATE_JSON_KEY")
            out[k]=v
        return out
    return json.loads(raw,object_pairs_hook=unique),hashlib.sha256(raw).hexdigest()


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--gateway",required=True)
    p.add_argument("--secondary",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    g,gh=load(a.gateway)
    s,sh=load(a.secondary)
    result=audit(g,s)
    result.update(gateway_file_sha256=gh,secondary_file_sha256=sh)
    Path(a.output).write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")


if __name__=="__main__":
    main()
