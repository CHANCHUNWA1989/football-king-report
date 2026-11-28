"""Read-only provenance completeness audit for public as-of snapshots.

This does not authenticate a publisher, infer a competition, repair a fixture,
change a forecast, or authorize production. Existing snapshot bytes stay intact.
"""
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

LEAGUES = {"epl", "championship", "bundesliga", "laliga", "seriea", "ligue1"}
FIELDS = ("league", "event_id", "home", "away", "source", "source_url",
          "source_captured_utc", "kickoff_utc")


def utc(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_UTC")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("NAIVE_TIME")
    return stamp.astimezone(timezone.utc)


def nonblank(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def audit(doc):
    if (not isinstance(doc, dict) or doc.get("schema") != "football-king-public-asof-1"
            or doc.get("production_recommendations") != "DISABLED"):
        raise ValueError("INVALID_RESEARCH_SNAPSHOT")
    rows = doc.get("observations")
    if (not isinstance(rows, list) or len(rows) > 1200
            or type(doc.get("event_count")) is not int or doc["event_count"] != len(rows)
            or any(not isinstance(r, dict) for r in rows)):
        raise ValueError("INVALID_OBSERVATIONS")
    raw = json.dumps(rows, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    if doc.get("observations_sha256") != digest:
        raise ValueError("OBSERVATION_DIGEST_MISMATCH")
    checked = utc(doc["as_of_utc"])
    missing = Counter({f: 0 for f in FIELDS})
    rejected = Counter()
    keys = Counter((r["league"], r["event_id"]) for r in rows
                   if isinstance(r.get("league"), str) and r["league"] in LEAGUES
                   and nonblank(r.get("event_id")))
    ready = 0
    for r in rows:
        absent = [f for f in FIELDS if not nonblank(r.get(f))]
        missing.update(absent)
        if absent:
            rejected["MISSING_EXPLICIT_FIELDS"] += 1
            continue
        if r["league"] not in LEAGUES or r["home"] == r["away"]:
            rejected["INVALID_COMPETITION_OR_TEAMS"] += 1
            continue
        if keys[(r["league"], r["event_id"])] != 1:
            rejected["AMBIGUOUS_EVENT_ID"] += 1
            continue
        try:
            captured = utc(r["source_captured_utc"])
            kickoff = utc(r["kickoff_utc"])
            if captured > checked or (kickoff - checked).total_seconds() <= 600:
                raise ValueError("CLOCK_ORDER")
        except (TypeError, ValueError, OverflowError):
            rejected["INVALID_OR_LATE_CLOCK"] += 1
            continue
        if r.get("eligible_for_prematch_evaluation") is not True or not r["source_url"].startswith("https://"):
            rejected["NOT_PREMATCH_OR_MISSING_HTTPS_SOURCE"] += 1
            continue
        ready += 1
    return {"schema": "football-king-public-snapshot-identity-audit-v1",
            "run_id": doc.get("run_id"), "as_of_utc": doc["as_of_utc"],
            "observations_sha256": digest, "observation_count": len(rows),
            "missing_fields": dict(missing), "rejected": dict(rejected),
            "explicit_identity_metadata_ready": ready,
            "source_identity_authenticated": False,
            "missing_gateway_fixtures_proven": False,
            "admitted_new_fixtures": 0, "production_recommendations": "DISABLED",
            "status": "HOLD"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--snapshot", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    with Path(a.snapshot).open("rb") as f:
        raw = f.read(8_000_001)
    if len(raw) > 8_000_000:
        raise ValueError("SNAPSHOT_TOO_LARGE")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    result = audit(json.loads(raw, object_pairs_hook=unique))
    Path(a.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
