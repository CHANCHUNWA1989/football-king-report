"""Fail-closed sealed-evidence integrity audit for offline football research.

A self-declared verification flag is not independent evidence. This module
reports missing provenance and time/market gaps; it never certifies EV or ROI.
"""
import argparse
import json
import math
from collections import Counter
from datetime import datetime, timezone


def _time(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_TIMESTAMP")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        raise ValueError("INVALID_TIMESTAMP") from None
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return dt.astimezone(timezone.utc)


def _prob(p):
    return (isinstance(p, list) and len(p) == 3
            and all(type(x) in (int, float) and math.isfinite(x)
                    and 0 <= x <= 1 for x in p)
            and abs(sum(p) - 1) <= 0.002)


def audit(payload, *, max_market_age_minutes=120):
    base = {"status": "HOLD", "production_recommendations": "DISABLED",
            "positive_ev_verified": False, "betting_roi_estimable": False,
            "independent_provenance_verified": False}
    if type(max_market_age_minutes) not in (int, float) or not math.isfinite(max_market_age_minutes) or max_market_age_minutes < 0:
        return {**base, "reason": "INVALID_MARKET_AGE_LIMIT"}
    if not isinstance(payload, dict) or payload.get("schema") != "football-king-forward-research-1":
        return {**base, "reason": "INVALID_EVIDENCE_SCHEMA"}
    samples = payload.get("samples")
    if not isinstance(samples, list) or len(samples) > 50000:
        return {**base, "reason": "INVALID_SAMPLES"}
    seen = set()
    counts = Counter()
    leagues = Counter()
    failures = Counter()
    for row in samples:
        counts["total"] += 1
        if not isinstance(row, dict):
            failures["invalid_row"] += 1
            continue
        key = row.get("key")
        if not isinstance(key, str) or not key.strip() or key in seen:
            failures["duplicate_or_missing_key"] += 1
        else:
            seen.add(key)
        if row.get("production_recommendations") != "DISABLED":
            failures["unsafe_production_flag"] += 1
        if row.get("fixture_result_source_independently_verified") is not True:
            counts["unverified_results"] += 1
        else:
            counts["self_declared_verified_results"] += 1
        league = row.get("league")
        if isinstance(league, str) and league.strip():
            leagues[league] += 1
        else:
            failures["invalid_league"] += 1
        if type(row.get("y")) is not int or row["y"] not in (0, 1, 2):
            failures["invalid_outcome"] += 1
        if not _prob(row.get("p")) or not _prob(row.get("m")):
            failures["invalid_probabilities"] += 1
        try:
            kickoff, forecast, market = (_time(row["kickoff_utc"]),
                                         _time(row["forecast_utc"]),
                                         _time(row["market_utc"]))
            if not market <= forecast < kickoff:
                failures["lookahead_or_market_after_forecast"] += 1
            else:
                counts["chronologically_valid"] += 1
                age = (forecast - market).total_seconds() / 60
                if age > max_market_age_minutes:
                    counts["stale_market_at_forecast"] += 1
                else:
                    counts["market_within_age_limit"] += 1
        except (KeyError, ValueError, TypeError, OverflowError):
            failures["invalid_timestamps"] += 1
    return {**base,
            "reason": "UNVERIFIED_EXTERNAL_RESULT_AND_QUOTE_PROVENANCE",
            "sample_count": counts["total"],
            "unverified_results": counts["unverified_results"],
            "self_declared_verified_results": counts["self_declared_verified_results"],
            "chronologically_valid": counts["chronologically_valid"],
            "stale_market_at_forecast": counts["stale_market_at_forecast"],
            "market_within_age_limit": counts["market_within_age_limit"],
            "max_market_age_minutes": max_market_age_minutes,
            "league_counts": dict(sorted(leagues.items())),
            "invalid_record_counts": dict(sorted(failures.items())),
            "note": "Market age is a diagnostic threshold, not a quote-authenticity proof; flags cannot certify source independence."}


def _unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("DUPLICATE_JSON_KEY")
        out[key] = value
    return out


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="evidence/settled.json")
    parser.add_argument("--max-market-age-minutes", type=float, default=120)
    args = parser.parse_args(argv)
    with open(args.input, encoding="utf-8") as f:
        payload = json.load(f, object_pairs_hook=_unique_pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))
    print(json.dumps(audit(payload, max_market_age_minutes=args.max_market_age_minutes),
                     indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
