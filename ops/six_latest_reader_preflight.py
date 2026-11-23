"""Six-publisher latest JSON read compatibility / age preflight (OFFLINE ONLY).

Both snapshots are caller-supplied local directories. Fixed allowlisted paths,
strict schema/UTC clock/JSON checks, no network, no writes, no fallback to
main/history, no verification of raw bookmaker data or independent scores.
Research age budgets are REVIEW thresholds, not publisher guarantees.
Every CLI invocation stays HOLD / DISABLED even when shape/age checks pass.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

MAX_BYTES = 1024 * 1024
UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|\+00:00)\Z")
DAY = 24 * 60

# Ceiling minutes are deliberately conservative RESEARCH review thresholds,
# not a guarantee of source freshness or permission to publish.
STREAMS = {
    "sources/hkjc_tipsme_free_latest.json": (
        "football-king-hkjc-tipsme-free-research-v1", "captured_utc", 2 * DAY,
        {"can_execute_bet": False, "not_executable_odds": True,
         "automatic_model_change": False}),
    "sources/latest.json": (
        "football-king-extra-source-audit-v1", "collected_utc", 12 * 60,
        {"six_league_independent_results_verified": False,
         "odds_fallback_confirmed": False}),
    "sources/live_germany_latest.json": (
        "football-king-openligadb-hourly-v1", "collected_utc", 3 * 60,
        {"replaces_bookmaker_market": False, "used_to_refit_model": False,
         "six_league_results_independently_verified": False}),
    "sources/seven_quality_gates_latest.json": (
        "football-king-seven-evidence-gates-v1", "captured_utc", 2 * DAY,
        {"can_promote_model": False, "can_recommend_bets": False}),
    "sources/six_league_fixture_overlap_latest.json": (
        "football-king-six-league-two-publisher-fixtures-v1",
        "captured_utc", 2 * DAY,
        {"model_promotion_authorized": False,
         "all_six_leagues_independently_verified": False}),
    "sources/six_league_free_latest.json": (
        "football-king-six-free-league-quality-v1", "captured_utc", 2 * DAY,
        {"automatic_model_change": False,
         "out_of_sample_edge_verified": False,
         "raw_bookmaker_quotes_published": False}),
}
SIX_LEAGUE_GROUP = (
    "sources/seven_quality_gates_latest.json",
    "sources/six_league_fixture_overlap_latest.json",
    "sources/six_league_free_latest.json",
)


class LatestReadHold(ValueError):
    """Short fixed error codes; never include original JSON, URLs or tokens."""


def _utc(value):
    if not isinstance(value, str) or not UTC.fullmatch(value):
        raise LatestReadHold("INVALID_UTC_TIMESTAMP")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError as exc:
        raise LatestReadHold("INVALID_UTC_TIMESTAMP") from exc


def _pairs(pairs):
    result = {}
    for key, val in pairs:
        if key in result:
            raise LatestReadHold("DUPLICATE_JSON_KEY")
        result[key] = val
    return result


def _nonfinite(value):
    raise LatestReadHold("NONFINITE_JSON_NUMBER")


def _read(root, name):
    path = root / name
    if root.is_symlink() or not root.is_dir() or path.is_symlink() or not path.is_file():
        raise LatestReadHold("MISSING_OR_UNSAFE_LATEST_POINTER")
    # Reject symlinked intermediate folders too, not only final JSON.
    if any((root / part).is_symlink() for part in ("sources",)):
        raise LatestReadHold("UNSAFE_LATEST_SOURCE_DIRECTORY")
    if not 0 < path.stat().st_size <= MAX_BYTES:
        raise LatestReadHold("LATEST_POINTER_SIZE_OUT_OF_BOUNDS")
    raw = path.read_bytes()
    if not 0 < len(raw) <= MAX_BYTES:
        raise LatestReadHold("LATEST_POINTER_SIZE_OUT_OF_BOUNDS")
    try:
        document = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_pairs, parse_constant=_nonfinite,
        )
    except (UnicodeError, ValueError, TypeError) as exc:
        raise LatestReadHold("INVALID_LATEST_JSON") from exc
    if not isinstance(document, dict):
        raise LatestReadHold("INVALID_LATEST_DOCUMENT_SHAPE")
    return document, hashlib.sha256(raw).hexdigest()


def _snapshot(root):
    docs, hashes, times = {}, {}, {}
    for name, (schema, time_key, _, safety) in STREAMS.items():
        doc, digest = _read(root, name)
        if doc.get("schema") != schema or doc.get("production_recommendations") != "DISABLED":
            raise LatestReadHold("LATEST_SCHEMA_OR_SAFETY_FLAG_MISMATCH")
        if doc.get("status") not in {"RESEARCH_ONLY", "HOLD", "NOT_CONFIGURED"}:
            raise LatestReadHold("UNREVIEWED_LATEST_STATUS")
        for key, required in safety.items():
            if type(doc.get(key)) is not bool or doc[key] is not required:
                raise LatestReadHold("UNAPPROVED_SOURCE_SAFETY_PROMOTION")
        docs[name], hashes[name], times[name] = doc, digest, _utc(doc.get(time_key))
    if len({times[name] for name in SIX_LEAGUE_GROUP}) != 1:
        raise LatestReadHold("SIX_LEAGUE_SNAPSHOT_SPLIT")
    return docs, hashes, times


def inspect(baseline_root, candidate_root, now_utc):
    """Read-only compare for exactly 6 source pointers, no release approval."""
    now = _utc(now_utc)
    baseline_root, candidate_root = Path(baseline_root), Path(candidate_root)
    old, old_hash, old_time = _snapshot(baseline_root)
    new, new_hash, new_time = _snapshot(candidate_root)
    records = []
    for name, (_, _, budget, _) in STREAMS.items():
        if new_time[name] < old_time[name]:
            raise LatestReadHold("LATEST_POINTER_CLOCK_ROLLBACK")
        age = (now - new_time[name]).total_seconds()
        if age < 0:
            raise LatestReadHold("LATEST_POINTER_FUTURE_TIMESTAMP")
        if age > budget * 60:
            raise LatestReadHold("LATEST_POINTER_OUTSIDE_RESEARCH_AGE_BUDGET")
        records.append({
            "path": name,
            "baseline_sha256": old_hash[name],
            "candidate_sha256": new_hash[name],
            "timestamp_utc": new_time[name].isoformat(),
            "baseline_timestamp_utc": old_time[name].isoformat(),
            "age_seconds": round(age),
            "review_age_ceiling_minutes": budget,
            "status": new[name]["status"],
            "schema_match": True,
            "timestamp_nonregressing": True,
            "byte_identical_to_baseline": old_hash[name] == new_hash[name],
        })
    return {
        "schema": "football-king-six-latest-read-preflight-v1",
        "status": "HOLD_SIX_LATEST_RESEARCH_READ_PREFLIGHT_ONLY",
        "snapshot_count": len(records),
        "records": records,
        "six_league_timestamp_consistent": True,
        "source_content_independently_authenticated": False,
        "tradable_market_freshness_verified": False,
        "historical_blob_retention_verified": False,
        "mobile_consumer_cutover_authorized": False,
        "hosted_archive_write_authorized": False,
        "production_recommendations": "DISABLED",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--now-utc", required=True)
    args = parser.parse_args(argv)
    try:
        receipt = inspect(args.baseline_root, args.candidate_root, args.now_utc)
    except (LatestReadHold, OSError, ValueError, TypeError):
        print(json.dumps({
            "status": "HOLD_SIX_LATEST_PREFLIGHT_NOT_VERIFIABLE",
            "production_recommendations": "DISABLED",
            "mobile_consumer_cutover_authorized": False,
        }, sort_keys=True))
        return 1
    print(json.dumps(receipt, sort_keys=True))
    # No green exit code until a different independently reviewed release gate.
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
