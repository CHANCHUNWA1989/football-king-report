"""Private-runner adapter: real normalized quotes -> research pairing.

Never export raw odds, candidate EVs, team names, fixture IDs or bookmaker IDs.
No forecasts are invented when the independent forecast feed is missing.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from ops.private_h2h_evidence import FEED_SCHEMA, verify_bound_quotes
from ops.private_forecast_quote_pair import SCHEMA, pair

OUTPUT_SCHEMA = "football-king-private-pair-aggregate-v1"


def aggregate(feed, forecasts=None, *, now=None):
    now = now or datetime.now(timezone.utc)
    result = {"schema": OUTPUT_SCHEMA, "status": "HOLD",
              "production_recommendations": "DISABLED",
              "positive_ev_verified": False, "candidate_details_exported": False,
              "raw_odds_exported": False}
    if not isinstance(feed, dict) or feed.get("schema") != FEED_SCHEMA or feed.get("production_recommendations") != "DISABLED":
        return {**result, "reason": "INVALID_PRIVATE_FEED"}
    raw = feed.get("quotes")
    if not isinstance(raw, list):
        return {**result, "reason": "INVALID_PRIVATE_QUOTES"}
    accepted, rejected = verify_bound_quotes(raw, now=now)
    result["validated_private_quote_count"] = len(accepted)
    result["rejected_private_quote_count"] = sum(rejected.values())
    if not forecasts:
        return {**result, "reason": "NO_INDEPENDENT_FORECAST_INPUT"}
    if not isinstance(forecasts, list):
        return {**result, "reason": "INVALID_FORECAST_INPUT"}
    rows = []
    for q in accepted:
        selection = {"HOME": "H", "DRAW": "D", "AWAY": "A"}.get(
            "HOME" if q["selection"] == q["home"] else
            "AWAY" if q["selection"] == q["away"] else
            "DRAW" if q["selection"] == "Draw" else "INVALID")
        if selection not in ("H", "D", "A"):
            return {**result, "reason": "INVALID_BOUND_SELECTION"}
        # Derived quote identity stays local and is never included in output.
        quote_id = hashlib.sha256(json.dumps(
            [q["fixture_id"], q["source"], q["selection"], q["observed_utc"],
             q["captured_utc"]], separators=(",", ":")).encode()).hexdigest()
        rows.append({"fixture_id": q["fixture_id"], "kickoff_utc": q["kickoff_utc"],
                     "observed_utc": q["captured_utc"], "market": "h2h",
                     "selection": selection, "decimal_odds": q["decimal_odds"],
                     "source": q["source"], "quote_id": quote_id})
    paired = pair({"schema": SCHEMA, "production_recommendations": "DISABLED",
                   "forecasts": forecasts, "quotes": rows}, now=now)
    return {**result, "reason": paired.get("reason", "PAIRING_FAILED"),
            "paired_research_quote_count": paired.get("paired_research_quotes", 0),
            "pairing_status": paired["status"]}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-feed", required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--private-forecasts")
    group.add_argument("--private-refit-report")
    group.add_argument("--private-history")
    parser.add_argument("--research-model", choices=("poisson", "dixon_coles"), default="poisson")
    parser.add_argument("--aggregate-output", required=True)
    args = parser.parse_args()
    try:
        feed = json.loads(Path(args.private_feed).read_text(encoding="utf-8"))
        forecasts = (json.loads(Path(args.private_forecasts).read_text(encoding="utf-8"))
                     if args.private_forecasts and Path(args.private_forecasts).is_file() else None)
        if args.private_refit_report:
            from ops.private_refit_forecast_adapter import adapt
            refit_path = Path(args.private_refit_report)
            if not refit_path.is_file():
                raise ValueError("MISSING_REFIT_REPORT")
            forecasts = adapt(json.loads(refit_path.read_text(encoding="utf-8")))
        if args.private_history:
            from ops.private_live_refit import build
            from ops.private_history_intake import load
            research = build(feed, load(args.private_history),
                             model=args.research_model)
            if research["status"] != "RESEARCH_ONLY":
                report = {"schema": OUTPUT_SCHEMA, "status": "HOLD",
                          "reason": research["reason"],
                          "production_recommendations": "DISABLED",
                          "positive_ev_verified": False,
                          "candidate_details_exported": False,
                          "raw_odds_exported": False}
            else:
                forecasts = research["forecasts"]
                report = aggregate(feed, forecasts)
        else:
            report = aggregate(feed, forecasts)
    except (OSError, ValueError, TypeError):
        report = {"schema": OUTPUT_SCHEMA, "status": "HOLD",
                  "reason": "PRIVATE_INPUT_READ_FAILURE",
                  "production_recommendations": "DISABLED",
                  "positive_ev_verified": False,
                  "candidate_details_exported": False,
                  "raw_odds_exported": False}
    target = Path(args.aggregate_output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print("PRIVATE_PAIR_STATUS:", report["status"], report["reason"])


if __name__ == "__main__":
    main()
