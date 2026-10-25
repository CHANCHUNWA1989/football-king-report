"""Private ephemeral odds collector for the all-market screener.

Raw quotes stay in the ephemeral Actions workspace, never in public artifacts,
commits or GitHub Pages. No inferred model probabilities or source certification.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from ops.odds_market import retrieve, verify, may_spend, APIProblem, SPORTS
from ops.private_h2h_evidence import FEED_SCHEMA, bind_response

def collect(key, now=None):
    # An explicit clock is a fixed offline/replay cutoff. Production must
    # timestamp each response after retrieval, not before a slow API batch.
    if now is not None:
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise ValueError("INVALID_COLLECTION_CLOCK")
        now = now.astimezone(timezone.utc)
    catalog = verify(key)
    quota = catalog["quota"]
    rows, coverage = [], []
    attempted, first_error, quota_blocked = False, None, False
    for league, sport in SPORTS.items():
        if not catalog["supported"].get(league) or not catalog["active"].get(league):
            coverage.append({"league": league, "reason": "NOT_AVAILABLE"})
            continue
        if not may_spend(quota):
            coverage.append({"league": league, "reason": "QUOTA_GUARD"})
            quota_blocked = True
            break
        try:
            events, quota = retrieve("/sports/"+sport+"/odds/", key, params={
                "regions": "eu", "markets": "h2h",
                "oddsFormat": "decimal", "dateFormat": "iso"})
        except APIProblem as e:
            first_error = first_error or str(e)
            coverage.append({"league": league, "reason": str(e)})
            if str(e) in ("RATE_LIMITED", "KEY_REJECTED_OR_NOT_AUTHORIZED", "SPORT_OR_PLAN_NOT_AUTHORIZED"):
                break
            continue
        if not isinstance(events, list) or quota.get("remaining") is None:
            coverage.append({"league": league, "reason": "BAD_RESPONSE_OR_QUOTA"})
            break
        captured = now if now is not None else datetime.now(timezone.utc)
        attempted = True
        # Reuse this exact completed response: no new request or market spend.
        bound = bind_response(events, league=league, sport=sport, captured=captured)
        rows.extend(bound["quotes"])
        coverage.append({"league": league, "quotes": len(bound["quotes"]),
                         "content_rejections": bound["rejected"]})
    status = ("CONNECTED" if attempted else "QUOTA_GUARD" if quota_blocked
              else "PROVIDER_ERROR" if first_error else "NO_ACTIVE_LEAGUES")
    return {"schema": FEED_SCHEMA, "quotes": rows, "coverage": coverage, "source": "The Odds API private research",
            "collector_status": status, "collector_reason": first_error,
            "production_recommendations": "DISABLED", "requested_markets": ["h2h"],
            "other_markets_status": "NOT_REQUESTED_FREE_QUOTA_GUARD"}

def main():
    key = os.environ.get("THE_ODDS_API_KEY", "")
    if not key:
        result = {"schema": FEED_SCHEMA, "quotes": [], "coverage": [], "collector_status": "MISSING_API_KEY",
                  "collector_reason": "THE_ODDS_API_KEY_NOT_CONFIGURED",
                  "production_recommendations": "DISABLED"}
    else:
        try:
            result = collect(key)
        except (APIProblem, ValueError, TypeError) as e:
            # Never serialize provider exceptions, URLs, credentials or response bodies.
            result = {"schema": FEED_SCHEMA, "quotes": [], "coverage": [], "collector_status": "PROVIDER_ERROR",
                      "collector_reason": "COLLECTOR_EXCEPTION_" + type(e).__name__,
                      "production_recommendations": "DISABLED"}
    target = Path("output/private_all_market_quotes.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print("COLLECTOR_STATUS:", result["collector_status"], "QUOTES:", len(result["quotes"]))

if __name__ == "__main__":
    main()
