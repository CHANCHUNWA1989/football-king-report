"""Screenshot-only 1X2 market research. No live data or model inference.

The supplied prices are manually transcribed, never provider-verified.
"""
import json
import argparse
from pathlib import Path


def analyze(snapshot):
    if not isinstance(snapshot, dict):
        raise ValueError("INVALID_SNAPSHOT")
    names = ("home", "draw", "away")
    prices = snapshot.get("decimal_odds")
    if not isinstance(prices, dict) or any(type(prices.get(k)) not in (float, int) or not 1 < prices[k] < 1000 for k in names):
        raise ValueError("INVALID_DECIMAL_ODDS")
    implied = {k: 1.0 / prices[k] for k in names}
    total = sum(implied.values())
    normalized = {k: round(implied[k] / total, 4) for k in names}
    return {
        "schema": "football-king-screenshot-market-research-v1",
        "fixture_label": snapshot.get("fixture_label"),
        "snapshot_at_local": snapshot.get("snapshot_at_local"),
        "score_label": snapshot.get("score_label"),
        "market": "h2h",
        "decimal_odds": {k: prices[k] for k in names},
        "raw_implied_probabilities": {k: round(implied[k], 4) for k in names},
        "overround": round(total - 1, 4),
        "normalized_market_probabilities": normalized,
        "status": "HOLD",
        "blockers": [
            "SCREENSHOT_ONLY_NOT_AUTHENTICATED_PROVIDER",
            "EXACT_MATCH_MINUTE_UNVERIFIED",
            "LIVE_STATS_AND_LINEUPS_UNVERIFIED",
            "NO_INDEPENDENT_MODEL_PROBABILITIES",
            "NO_VERIFIED_POSITIVE_EV",
        ],
        "score_prediction": None,
        "production_recommendations": "DISABLED",
        "betting_permission": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    snapshot = json.loads(Path(args.input).read_text(encoding="utf-8"))
    report = analyze(snapshot)
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "blockers": report["blockers"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
