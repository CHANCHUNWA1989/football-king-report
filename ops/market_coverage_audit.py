"""Research-only market coverage audit. Never infer missing handicap/total prices."""
import argparse
import json
from pathlib import Path

MARKETS = ("h2h", "spreads", "totals")


def audit(market_snapshot, private_summary):
    if not isinstance(market_snapshot, dict) or not isinstance(private_summary, dict):
        raise ValueError("INVALID_INPUT")
    requested = private_summary.get("requested_markets", [])
    if not isinstance(requested, list):
        raise ValueError("INVALID_MARKET_LIST")
    observed = tuple(m for m in MARKETS if m in requested)
    missing = [m for m in MARKETS if m not in observed]
    return {
        "schema": "football-king-market-coverage-audit-v1",
        "as_of_utc": market_snapshot.get("as_of_utc"),
        "requested_markets": list(observed),
        "missing_markets": missing,
        "market_coverage_complete": not missing,
        "handicap_available": "spreads" in observed,
        "totals_available": "totals" in observed,
        "raw_prices_verified": False,
        "can_recommend_handicap_or_totals": False,
        "reason": "MISSING_MARKET_COLLECTION" if missing else "PRICE_AND_MODEL_VALIDATION_REQUIRED",
        "production_recommendations": "DISABLED",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", default="market/latest.json")
    parser.add_argument("--summary", default="market/private_summary_latest.json")
    parser.add_argument("--output", default="market/coverage_audit.json")
    args = parser.parse_args()
    report = audit(json.loads(Path(args.market).read_text()),
                   json.loads(Path(args.summary).read_text()))
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"missing_markets": report["missing_markets"],
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
