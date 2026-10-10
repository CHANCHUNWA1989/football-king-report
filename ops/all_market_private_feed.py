"""Private ephemeral odds collector for the all-market screener.

Raw quotes are kept only in the Actions workspace/artifact. Never commit them
or publish to GitHub Pages. No inferred model probabilities.
"""
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from ops.odds_market import retrieve, verify, may_spend, utc, APIProblem, SPORTS

def collect(key, now=None):
    now = now or datetime.now(timezone.utc)
    catalog = verify(key)
    quota = catalog["quota"]
    rows, coverage = [], []
    for league, sport in SPORTS.items():
        if not catalog["supported"].get(league) or not catalog["active"].get(league):
            coverage.append({"league": league, "reason": "NOT_AVAILABLE"})
            continue
        if not may_spend(quota):
            coverage.append({"league": league, "reason": "QUOTA_GUARD"})
            break
        try:
            events, quota = retrieve("/sports/"+sport+"/odds/", key, params={
                "regions": "eu", "markets": "h2h,spreads,totals",
                "oddsFormat": "decimal", "dateFormat": "iso"})
        except APIProblem as e:
            coverage.append({"league": league, "reason": str(e)})
            if str(e) in ("RATE_LIMITED", "KEY_REJECTED_OR_NOT_AUTHORIZED", "SPORT_OR_PLAN_NOT_AUTHORIZED"):
                break
            continue
        if not isinstance(events, list) or quota.get("remaining") is None:
            coverage.append({"league": league, "reason": "BAD_RESPONSE_OR_QUOTA"})
            break
        count = 0
        for event in events[:500]:
            if not isinstance(event, dict):
                continue
            try:
                kickoff = utc(event["commence_time"])
            except (KeyError, ValueError, TypeError, AttributeError):
                continue
            if not now + timedelta(minutes=10) < kickoff < now + timedelta(days=7):
                continue
            for book in event.get("bookmakers", [])[:100]:
                if not isinstance(book, dict) or not isinstance(book.get("key"), str):
                    continue
                for market in book.get("markets", [])[:20]:
                    if not isinstance(market, dict) or market.get("key") not in ("h2h", "spreads", "totals"):
                        continue
                    try:
                        observed = utc(market.get("last_update") or book.get("last_update"))
                    except (TypeError, ValueError, AttributeError):
                        continue
                    if not timedelta(seconds=-60) <= now-observed <= timedelta(minutes=20):
                        continue
                    for outcome in market.get("outcomes", [])[:50]:
                        if not isinstance(outcome, dict):
                            continue
                        price = outcome.get("price")
                        if type(price) not in (float, int) or not 1.01 <= price <= 100:
                            continue
                        line = outcome.get("point", 0)
                        if type(line) not in (float, int):
                            continue
                        rows.append({
                            "fixture_id": str(event.get("id", "")),
                            "league": league, "home": event.get("home_team"),
                            "away": event.get("away_team"), "market": market["key"],
                            "selection": outcome.get("name"), "line": line,
                            "decimal_odds": price, "source": book["key"],
                            "observed_utc": observed.isoformat(),
                            "kickoff_utc": kickoff.isoformat(),
                            "source_verified": True,
                            "independently_calibrated": False,
                            "lineup_checked": False})
                        count += 1
        coverage.append({"league": league, "quotes": count})
    return {"quotes": rows, "coverage": coverage, "source": "The Odds API private research", "production_recommendations": "DISABLED"}

def main():
    key = os.environ.get("THE_ODDS_API_KEY", "")
    if not key:
        print("NO_API_KEY")
        return
    try:
        result = collect(key)
    except APIProblem as e:
        print("COLLECTOR_HOLD:", str(e))
        return
    target = Path("output/private_all_market_quotes.json")
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print("PRIVATE_QUOTES:", len(result["quotes"]), "LEAGUES:", result["coverage"])

if __name__ == "__main__":
    main()
