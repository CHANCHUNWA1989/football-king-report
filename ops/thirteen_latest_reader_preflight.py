"""Thirteen pinned status readers: observation only, never select live inputs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from ops.history_blob_retention_preflight import _git, _valid_sha, RetentionHold
from ops.six_latest_reader_preflight import STREAMS, SIX_LEAGUE_GROUP, _utc, _pairs, _nonfinite, LatestReadHold

# (schema, clock, research-age minutes, required flags, status field, statuses)
# Fixed review ceilings, not a source freshness SLA or trade authorization.
CONTRACTS = {k: (*v, "status", ("RESEARCH_ONLY", "HOLD", "NOT_CONFIGURED"))
             for k, v in STREAMS.items()}
CONTRACTS.update({
    "market/collection_status.json": (
        "football-king-free-market-collection-status-v1", "as_of_utc", 720,
        {}, "collection_status", ("HOLD", "RESEARCH_ONLY")),
    "market/japan_free_status.json": (
        "football-king-japan-free-market-research-v1", "collected_utc", 2880,
        {"realtime_inplay_quotes_confirmed": False, "raw_bookmaker_prices_or_names_redistributed": False,
         "j1_model_remains_uncalibrated": True, "j1_fixtures_not_independently_verified": True,
         "estimated_roi": None, "bet_recommendation_count": 0}, "status", ("HOLD", "RESEARCH_ONLY")),
    "market/private_summary_latest.json": (
        "football-king-public-artifact-summary-v1", "captured_utc", 1440,
        {"raw_prices_or_bookmakers_included": False, "quotes_are_executable": False,
         "verified_bets": 0}, "input_status", ("QUOTA_GUARD", "HOLD", "RESEARCH_ONLY")),
    "sources/bsd_status_latest.json": (
        "football-king-bsd-free-research-v1", "captured_utc", 2880,
        {"raw_quotes_published": False, "licensed_per_bookmaker_prices_available": False,
         "independently_verified_market_advantage": False, "replaces_current_market_automatically": False},
        "status", ("NO_COMPARABLE_MARKET", "HOLD", "RESEARCH_ONLY", "NOT_CONFIGURED")),
    "sources/research_extensions_latest.json": (
        "football-king-free-research-extensions-v1", "completed_utc", 2880,
        {"no_provider_raw_data_redistributed": True, "new_model_variables_enabled": False,
         "historical_statsbomb_results_are_live": False, "current_free_odds_1x2_confirmed": False},
        "status", ("HOLD", "RESEARCH_ONLY")),
    "sources/weather_latest.json": (
        "football-king-metno-city-weather-v1", "captured_utc", 2880,
        {"source_data_used_in_model": False, "verified_betting_advantage": False,
         "current_executable_bookmaker_odds": False}, "status", ("HOLD", "RESEARCH_ONLY")),
    "sources/wide_latest.json": (
        "football-king-wide-free-leagues-v1", "collected_utc", 2880,
        {"results_independently_verified": False, "automatic_prediction_training": False,
         "market_odds_available": False}, "status", ("HOLD", "RESEARCH_ONLY")),
})
MAX_BYTES = 1024 * 1024


def read_pinned(repo, commit, path):
    if path not in CONTRACTS or not _valid_sha(commit):
        raise LatestReadHold("UNAPPROVED_POINTER_OR_PIN")
    entry = _git(repo, "ls-tree", "-z", commit, "--", path, limit=4096)
    if entry.count(b"\0") != 1 or not entry.endswith(b"\0"):
        raise LatestReadHold("MISSING_OR_AMBIGUOUS_POINTER")
    header, sep, filename = entry[:-1].partition(b"\t")
    fields = header.split()
    if not sep or filename != path.encode("ascii") or len(fields) != 3 or fields[:2] != [b"100644", b"blob"]:
        raise LatestReadHold("UNSAFE_POINTER_TREE_ENTRY")
    oid = fields[2].decode("ascii")
    if not _valid_sha(oid):
        raise LatestReadHold("INVALID_POINTER_BLOB")
    size = int(_git(repo, "cat-file", "-s", oid, limit=64))
    if not 0 < size <= MAX_BYTES:
        raise LatestReadHold("POINTER_SIZE_LIMIT")
    raw = _git(repo, "cat-file", "blob", oid, limit=MAX_BYTES)
    if len(raw) != size or hashlib.sha1(b"blob " + str(size).encode() + b"\0" + raw).hexdigest() != oid:
        raise LatestReadHold("POINTER_BLOB_MISMATCH")
    return raw, oid


def parse(path, raw):
    schema, clock, budget, flags, status_key, statuses = CONTRACTS[path]
    doc = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_pairs, parse_constant=_nonfinite)
    if type(doc) is not dict or doc.get("schema") != schema or doc.get("production_recommendations") != "DISABLED":
        raise LatestReadHold("SCHEMA_OR_SAFETY_MISMATCH")
    status = doc.get(status_key)
    if type(status) is not str or status not in statuses:
        raise LatestReadHold("UNREVIEWED_POINTER_STATUS")
    for key, val in flags.items():
        if key not in doc or type(doc[key]) is not type(val) or doc[key] != val:
            raise LatestReadHold("UNAPPROVED_POINTER_SAFETY_VALUE")
    ts = _utc(doc.get(clock))
    if path == "sources/research_extensions_latest.json" and _utc(doc.get("started_utc")) > ts:
        raise LatestReadHold("REVERSED_CAPTURE_CLOCK")
    return ts, status, budget


def inspect(repo, source, archive, candidate, now_utc):
    now = _utc(now_utc)
    for pin in (source, archive, candidate):
        if not _valid_sha(pin) or _git(repo, "cat-file", "-t", pin, limit=64).strip() != b"commit":
            raise LatestReadHold("INVALID_COMMIT_PIN")
    records = []
    clocks = {k: {} for k in ("source", "archive", "candidate")}
    for path in CONTRACTS:
        row = {"path": path, "compatible": False}
        try:
            old, old_oid = read_pinned(repo, archive, path)
            new, new_oid = read_pinned(repo, source, path)
            copy, copy_oid = read_pinned(repo, candidate, path)
            ot, os, _ = parse(path, old)
            nt, ns, budget = parse(path, new)
            ct, cs, _ = parse(path, copy)
            if copy != old or copy_oid != old_oid:
                raise LatestReadHold("CANDIDATE_MUTABLE_POINTER_CHANGED")
            if nt < ot:
                raise LatestReadHold("POINTER_CLOCK_ROLLBACK")
            if nt > now or ot > now:
                raise LatestReadHold("POINTER_FUTURE_CLOCK")
            if nt == ot and new != old:
                raise LatestReadHold("SAME_CLOCK_DIFFERENT_BYTES")
            for label, ts in (("source", nt), ("archive", ot), ("candidate", ct)):
                clocks[label][path] = ts
            age = (now - nt).total_seconds()
            row.update(compatible=True, source_blob=new_oid, archive_blob=old_oid,
                       candidate_blob=copy_oid, source_timestamp_utc=nt.isoformat(),
                       archive_timestamp_utc=ot.isoformat(), source_status=ns,
                       archive_status=os, source_age_seconds=round(age),
                       review_age_ceiling_minutes=budget,
                       freshness="WITHIN_RESEARCH_AGE" if age <= budget * 60 else "HOLD_STALE",
                       source_pointer_changed=new_oid != old_oid)
        except (ValueError, OSError, KeyError, TypeError, RuntimeError):
            # No raw payloads or untrusted exception strings in the receipt.
            row["reason"] = "HOLD_POINTER_CONTRACT_OR_PIN_FAILED"
        records.append(row)
    group_ok = all(all(p in c for p in SIX_LEAGUE_GROUP) and
                   len({c[p] for p in SIX_LEAGUE_GROUP}) == 1 for c in clocks.values())
    return dict(status="HOLD_THIRTEEN_POINTER_OBSERVATION_ONLY", source_sha=source,
                archive_sha=archive, candidate_sha=candidate, observed_utc=now.isoformat(),
                pointer_count=len(records), compatible_count=sum(r["compatible"] for r in records),
                stale_count=sum(r.get("freshness") == "HOLD_STALE" for r in records),
                six_league_timestamp_consistent=group_ok, records=records,
                source_switch_authorized=False, hosted_archive_write_authorized=False,
                independent_archive_retention_verified=False,
                tradable_market_freshness_verified=False, production_recommendations="DISABLED")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--archive", required=True)
    p.add_argument("--candidate", required=True)
    args = p.parse_args()
    try:
        result = inspect(args.repo, args.source, args.archive, args.candidate,
                         datetime.now(timezone.utc).isoformat())
    except (ValueError, OSError, KeyError, TypeError, RuntimeError):
        print(json.dumps(dict(status="HOLD_POINTER_OBSERVATION_FAILED", production_recommendations="DISABLED")))
        return 1
    print(json.dumps(result, sort_keys=True))
    # Success means observed compatible structure, never release or freshness.
    return 0 if result["compatible_count"] == 13 and result["six_league_timestamp_consistent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
