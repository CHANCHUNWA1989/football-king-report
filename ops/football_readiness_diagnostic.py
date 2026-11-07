"""Explain research readiness without exposing private bookmaker prices.

This is a *diagnostic*, not a selection model. No odds or bookmaker
identities are permitted in the input summary or output.
"""
from datetime import datetime, timezone

SCHEMA = "football-king-readiness-diagnostic-v1"
SUMMARY_SCHEMA = "football-king-public-artifact-summary-v1"


def _utc(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_CAPTURE_TIME")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("NAIVE_CAPTURE_TIME")
    return stamp.astimezone(timezone.utc)


def diagnose(summary, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    base = {"schema": SCHEMA, "status": "HOLD",
            "production_recommendations": "DISABLED",
            "verified_positive_ev": False,
            "model_prediction_completed": False,
            "recommendation_ready": False}
    if not isinstance(summary, dict) or summary.get("schema") != SUMMARY_SCHEMA:
        return {**base, "blockers": ["NO_SAFE_PRIVATE_FEED_SUMMARY"]}
    # An explicitly redacted summary only. Never echo provider data or quotes.
    try:
        observed = _utc(summary["captured_utc"])
        status = summary["input_status"]
        counts = summary["counts"]
        coverage = summary["coverage"]
        markets = summary["requested_markets"]
        progress = summary["evidence_progress"]
        if (type(status) is not str or not isinstance(counts, dict)
                or not isinstance(coverage, list)
                or not isinstance(markets, list)
                or not isinstance(progress, dict)):
            raise ValueError("BAD_REDACTED_SUMMARY")
        for k in ("RESEARCH_ONLY", "VERIFIED_VALUE", "STALE", "INCOMPLETE", "INVALID", "NO_VALUE"):
            if type(counts.get(k)) is not int or counts[k] < 0:
                raise ValueError("BAD_COUNT")
        if any(type(x) is not str for x in markets):
            raise ValueError("BAD_MARKETS")
        if (summary.get("production_recommendations") != "DISABLED"
                or summary.get("raw_prices_or_bookmakers_included") is not False
                or summary.get("quotes_are_executable") is not False
                or type(summary.get("verified_bets")) is not int
                or summary["verified_bets"] != 0):
            raise ValueError("UNSAFE_OR_UNREDACTED_SUMMARY")
        if any(not isinstance(x, dict) or type(x.get("quotes")) is not int or x["quotes"] < 0
               or type(x.get("league")) is not str for x in coverage):
            raise ValueError("BAD_COVERAGE")
        verified_results = progress["independently_verified_result_cases"]
        if type(verified_results) is not int or verified_results < 0:
            raise ValueError("BAD_EVIDENCE_COUNT")
        age = (now.astimezone(timezone.utc) - observed).total_seconds()
        blockers = []
        if status != "CONNECTED":
            blockers.append("PRIVATE_FEED_NOT_CONNECTED")
        if age < -60 or age > 3600:
            blockers.append("REDACTED_FEED_SUMMARY_STALE")
        if sum(x["quotes"] for x in coverage) == 0:
            blockers.append("ZERO_COLLECTED_QUOTES")
        if counts["RESEARCH_ONLY"] == 0:
            blockers.append("NO_RESEARCH_QUOTES")
        if set(markets) != {"h2h"}:
            blockers.append("MARKET_SCOPE_NOT_H2H_ONLY")
        else:
            blockers.append("ASIAN_HANDICAP_AND_TOTALS_NOT_COLLECTED")
        if verified_results == 0:
            blockers.append("NO_INDEPENDENTLY_VERIFIED_SETTLEMENTS")
        blockers.extend(["PRIVATE_QUOTES_NOT_IN_PUBLIC_DAILY_REPORT",
                         "LIVE_MODEL_FORECAST_AND_QUOTE_PAIRING_UNVERIFIED",
                         "INDEPENDENT_PROVENANCE_AND_RELEASE_GATES_UNMET"])
        return {**base, "input_status": status,
                "captured_utc": observed.isoformat(),
                "summary_age_seconds": round(age),
                "redacted_quote_count": sum(x["quotes"] for x in coverage),
                "league_count": len({x["league"] for x in coverage}),
                "requested_markets": ["h2h"] if set(markets) == {"h2h"} else [],
                "independently_verified_result_cases": verified_results,
                "blockers": blockers}
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return {**base, "blockers": ["INVALID_REDACTED_SUMMARY"]}


def main():
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", default="market/private_summary_latest.json")
    parser.add_argument("--output", default="output/football_readiness_diagnostic.json")
    args = parser.parse_args()
    try:
        src = Path(args.summary)
        data = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        data = None
    report = diagnose(data)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("READINESS:", report["status"], "BLOCKERS:", ",".join(report["blockers"]))


if __name__ == "__main__":
    main()
