"""Read-only readiness audit for time-locked football model calibration.

This CLI deliberately NEVER certifies provider claims by reading a JSON file:
verification of external source bytes, native identity and forecast sealing
requires a separate independently audited evidence pipeline. The archive is
potential research input, not authenticated model-scoring training material.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path

SCHEMA = "football-king-calibration-readiness-audit-v1"
MIN_CERTIFIED = 300
MIN_WEEKS = 12
MIN_LEAGUES = 4
MIN_PER_LEAGUE = 40
MAX_SIZE = 8_000_000


def _utc(value):
    if type(value) is not str or len(value) > 40:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        return None
    if result.tzinfo is None or result.utcoffset() is None:
        return None
    return result.astimezone(timezone.utc)


def _prob(value):
    return (type(value) in (tuple, list)
            and len(value) == 3
            and all(type(n) in (int, float) and math.isfinite(n)
                    and 0 < n < 1 for n in value)
            and abs(math.fsum(value) - 1) <= 1e-6)


def audit(payload):
    """Report archive coverage and BLOCK certified admission.

    Even all-True flags can be user-authored. The archive has no independent
    trusted evidence-verifier boundary, so this audit cannot certify any row.
    """
    result = {
        "schema": SCHEMA,
        "status": "HOLD",
        "reason": "EXTERNAL_ATTESTATION_AND_RESULT_VERIFICATION_NOT_INTEGRATED",
        "source_checked_utc": None,
        "archive_rows": 0,
        "research_pair_shape_rows": 0,
        "chronologically_ordered_research_rows": 0,
        "flag_claims": {
            "result_source_verified": 0,
            "fixture_identity_verified": 0,
            "forecast_independently_attested": 0,
            "all_three_claimed": 0,
        },
        "unsafe_or_incomplete_rows": 0,
        "duplicate_case_keys": 0,
        "research_league_counts": {},
        "certified_forward_rows": 0,
        "certified_distinct_weeks": 0,
        "certified_leagues_meeting_40_rows": 0,
        "remaining_to_300": MIN_CERTIFIED,
        "qualifies_for_calibration_training": False,
        "independent_source_verifier_present": False,
        "raw_provenance_authentication_performed": False,
        "calibration_performance_measured": False,
        "verified_positive_ev": False,
        "production_recommendations": "DISABLED",
    }
    if type(payload) is not dict or type(payload.get("samples")) is not list:
        result["reason"] = "INVALID_ARCHIVE_FORMAT"
        return result
    rows = payload["samples"]
    if len(rows) > 10000:
        result["reason"] = "OVERSIZED_ARCHIVE"
        return result
    result["source_checked_utc"] = payload.get("checked_utc")
    result["archive_rows"] = len(rows)
    flags = result["flag_claims"]
    per_league = Counter()
    seen = set()
    for row in rows:
        if type(row) is not dict:
            result["unsafe_or_incomplete_rows"] += 1
            continue
        league, key = row.get("league"), row.get("key")
        if type(key) is not str or not key or len(key) > 512:
            result["unsafe_or_incomplete_rows"] += 1
            continue
        if key in seen:
            result["duplicate_case_keys"] += 1
            continue
        seen.add(key)
        if type(league) is not str or not league or len(league) > 80:
            result["unsafe_or_incomplete_rows"] += 1
            continue
        p, m, y = row.get("p"), row.get("m"), row.get("y")
        if not (_prob(p) and _prob(m) and type(y) is int and y in (0, 1, 2)
                and row.get("production_recommendations") == "DISABLED"):
            result["unsafe_or_incomplete_rows"] += 1
            continue
        result["research_pair_shape_rows"] += 1
        per_league[league] += 1
        forecast = _utc(row.get("forecast_utc"))
        market = _utc(row.get("market_utc"))
        kickoff = _utc(row.get("kickoff_utc"))
        if (forecast is None or market is None or kickoff is None
                or not (forecast < kickoff and market < kickoff)):
            result["unsafe_or_incomplete_rows"] += 1
            continue
        result["chronologically_ordered_research_rows"] += 1
        claims = (
            row.get("fixture_result_source_independently_verified") is True,
            row.get("fixture_identity_independently_verified") is True,
            row.get("forecast_provenance_independently_attested") is True,
        )
        for key, is_true in zip(
                ("result_source_verified", "fixture_identity_verified",
                 "forecast_independently_attested"), claims):
            flags[key] += int(is_true)
        flags["all_three_claimed"] += int(all(claims))
        # Critical boundary: a self-asserted flag is NOT independent proof.
        # We NEVER report certified rows on JSON field claims alone.
    result["research_league_counts"] = dict(sorted(per_league.items()))
    result["reason"] = (
        "NO_AUTHENTICATED_PROSPECTIVE_PAIRS"
        if result["chronologically_ordered_research_rows"]
        else "NO_TIME_VALID_RESEARCH_PAIRS"
    )
    return result


def _reject_duplicates(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("DUPLICATE_JSON_KEY")
        obj[key] = value
    return obj


def read_archive(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_SIZE:
        raise ValueError("MISSING_OR_OVERSIZED_ARCHIVE")
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicates,
                      parse_constant=lambda _: (_ for _ in ()).throw(
                          ValueError("NONFINITE_JSON")))


def main(argv=None):
    parser = argparse.ArgumentParser()
    default = Path(__file__).resolve().parents[1] / "evidence" / "settled.json"
    parser.add_argument("--input", default=str(default))
    args = parser.parse_args(argv)
    try:
        result = audit(read_archive(args.input))
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as error:
        result = audit(None)
        result["read_error_class"] = type(error).__name__
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    # 0 = audit successfully ran and safely returned HOLD, not promotion.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
