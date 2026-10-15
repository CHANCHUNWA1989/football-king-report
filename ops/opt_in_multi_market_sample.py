"""Opt-in private multi-market sampling; never write raw bookmaker prices.

Runs one league per invocation, with strict provider quota and research-only output.
Not scheduled automatically: extra market types can consume paid credits.
"""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from odds_market import APIProblem, MIN_REMAINING, SPORTS, may_spend, retrieve, verify
from private_multi_market_audit import audit

MARKETS = "h2h,spreads,totals"


def collect_sample(key, league, *, opener=None, now=None):
    if league not in SPORTS:
        raise ValueError("UNSUPPORTED_LEAGUE")
    if not isinstance(key, str) or not key.strip():
        return {"status": "HOLD", "reason": "MISSING_KEY",
                "production_recommendations": "DISABLED"}
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    kwargs = {} if opener is None else {"opener": opener}
    check = verify(key, **kwargs)
    quota = check["quota"]
    # Reserve at least six credits for the three-market request. Actual cost
    # depends on provider/regions and is read from response headers afterward.
    if not may_spend(quota) or quota["remaining"] <= MIN_REMAINING + 6:
        return {"status": "HOLD", "reason": "QUOTA_RESERVE",
                "production_recommendations": "DISABLED"}
    if not check["supported"][league] or not check["active"][league]:
        return {"status": "HOLD", "reason": "LEAGUE_UNAVAILABLE",
                "production_recommendations": "DISABLED"}
    rows, billed = retrieve("/sports/" + SPORTS[league] + "/odds/", key,
                            params={"regions": "eu", "markets": MARKETS,
                                    "oddsFormat": "decimal", "dateFormat": "iso"},
                            **kwargs)
    if not isinstance(rows, list):
        raise APIProblem("BAD_ODDS_SCHEMA")
    if billed["remaining"] is None or billed["used"] is None:
        return {"status": "HOLD", "reason": "MISSING_QUOTA_HEADERS",
                "production_recommendations": "DISABLED"}
    if any(not isinstance(x, dict) or x.get("sport_key") != SPORTS[league]
           for x in rows):
        return {"status": "HOLD", "reason": "MISMATCHED_SPORT",
                "production_recommendations": "DISABLED"}
    result = audit(rows, now.isoformat())
    result["league"] = league
    result["quota"] = billed
    result["raw_prices_persisted"] = False
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", choices=tuple(SPORTS), required=True)
    parser.add_argument("--output", default="market/private_multi_market_audit.json")
    parser.add_argument("--ack-credit-cost", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate configuration without any provider request")
    args = parser.parse_args()
    if not args.dry_run and not args.ack_credit_cost:
        parser.error("Explicit --ack-credit-cost required; this can spend API credits")
    key = os.environ.get("THE_ODDS_API_KEY", "")
    try:
        if args.dry_run:
            result = {"status": "DRY_RUN", "league": args.league,
                      "markets_requested_if_approved": MARKETS.split(","),
                      "key_configured": bool(key.strip()),
                      "api_requests_made": 0,
                      "production_recommendations": "DISABLED"}
        else:
            result = collect_sample(key, args.league)
    except (APIProblem, ValueError) as exc:
        result = {"status": "HOLD", "reason": str(exc),
                  "production_recommendations": "DISABLED"}
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"status": result["status"],
                      "reason": result.get("reason"),
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
