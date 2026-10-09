"""Free-tier The Odds API V4 1X2 market research adapter.

Provider: https://the-odds-api.com (with hyphens), NOT theoddsapi.com.
Never log the API key, raw API URL, bookmaker prices or response body.
Only derived, de-vigged bookmaker-consensus probabilities are persisted.
NOT an automatic betting recommendation.
"""
import argparse
import json
import math
import os
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = "https://api.the-odds-api.com/v4"
SPORTS = {
    "epl": "soccer_epl",
    "championship": "soccer_efl_champ",
    "bundesliga": "soccer_germany_bundesliga",
    "laliga": "soccer_spain_la_liga",
    "seriea": "soccer_italy_serie_a",
    "ligue1": "soccer_france_ligue_one",
}
MAX_USED = 360
MIN_REMAINING = 140
MAX_BYTES = 5_000_000


class APIProblem(Exception):
    pass


def utc(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("NAIVE_TIME")
    return stamp.astimezone(timezone.utc)


def quota(headers):
    # Never infer quota from how many requests we sent. Trust provider counters.
    def read(name):
        value = headers.get(name)
        if value is None:
            return None
        try:
            n = int(value)
            return n if n >= 0 else None
        except (ValueError, TypeError):
            return None
    return {"used": read("x-requests-used"),
            "remaining": read("x-requests-remaining"),
            "last": read("x-requests-last")}


def may_spend(q):
    return (q.get("used") is not None and q.get("remaining") is not None
            and q["used"] < MAX_USED and q["remaining"] > MIN_REMAINING + 1)


def retrieve(path, key, *, opener=urlopen, params=None):
    if not key or not isinstance(key, str):
        raise APIProblem("MISSING_KEY")
    query = {"apiKey": key}
    query.update(params or {})
    # The URL includes an API secret, so never include a raw exception string in logs.
    url = ROOT + path + "?" + urlencode(query)
    request = Request(url, headers={"User-Agent": "FootballKingV41Research/1.0",
                                    "Accept": "application/json"})
    try:
        with opener(request, timeout=15) as response:
            raw = response.read(MAX_BYTES + 1)
            q = quota(response.headers)
        if len(raw) > MAX_BYTES:
            raise APIProblem("RESPONSE_TOO_LARGE")
        result = json.loads(raw)
        return result, q
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise APIProblem("KEY_REJECTED_OR_NOT_AUTHORIZED") from None
        if exc.code in (402, 422):
            raise APIProblem("SPORT_OR_PLAN_NOT_AUTHORIZED") from None
        if exc.code == 429:
            raise APIProblem("RATE_LIMITED") from None
        raise APIProblem("PROVIDER_HTTP_" + str(exc.code)) from None
    except (URLError, TimeoutError, OSError):
        raise APIProblem("PROVIDER_NETWORK_ERROR") from None
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        raise APIProblem("PROVIDER_BAD_JSON") from None


def verify(key, *, opener=urlopen):
    sports, q = retrieve("/sports/", key, opener=opener)
    if not isinstance(sports, list):
        raise APIProblem("BAD_SPORTS_CATALOG")
    available = {s.get("key"): bool(s.get("active", False)) for s in sports if isinstance(s, dict)}
    supported = {code: (SPORTS[code] in available) for code in SPORTS}
    active = {code: bool(available.get(key)) for code, key in SPORTS.items()}
    return {
        "connected": True,
        "provider": "the-odds-api.com/v4",
        "quota": q,
        "supported": supported,
        "active": active,
        "source_verified_with_secret": True,
        "production_recommendations": "DISABLED",
    }


def book_probabilities(book, home, away, now):
    """Return vig-free h2h for a single timely bookmaker or None."""
    if not isinstance(book, dict):
        return None
    for m in book.get("markets", []):
        if not isinstance(m, dict) or m.get("key") != "h2h":
            continue
        last = m.get("last_update") or book.get("last_update")
        try:
            updated = utc(last)
        except (ValueError, TypeError, AttributeError):
            continue
        age = (now - updated).total_seconds()
        if age < -300 or age > 8 * 3600:
            continue
        outcome_prices = {}
        for x in m.get("outcomes", []):
            if not isinstance(x, dict):
                continue
            name, price = x.get("name"), x.get("price")
            if name in (home, away, "Draw") and type(price) in (int, float):
                if math.isfinite(price) and 1.01 <= price <= 500:
                    outcome_prices[name] = float(price)
        if set(outcome_prices) != {home, away, "Draw"}:
            continue
        inverse = [1 / outcome_prices[name] for name in (home, "Draw", away)]
        overround = sum(inverse)
        if not (0.98 <= overround <= 1.35):
            continue
        return [x / overround for x in inverse], updated
    return None


def aggregate(event, *, now):
    if not isinstance(event, dict):
        return None
    home, away, event_id = event.get("home_team"), event.get("away_team"), event.get("id")
    if not all(isinstance(v, str) and 0 < len(v) < 150 for v in (home, away, event_id)):
        return None
    if home == away:
        return None
    try:
        kickoff = utc(event["commence_time"])
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    # Do not mix in-play or already completed games with pre-match odds.
    if not now + timedelta(minutes=10) < kickoff <= now + timedelta(days=21):
        return None
    per_book = {}
    for book in event.get("bookmakers", [])[:100]:
        if not isinstance(book, dict):
            continue
        key = book.get("key")
        if not isinstance(key, str) or not key:
            continue
        val = book_probabilities(book, home, away, now)
        if val:
            per_book[key] = val
    if len(per_book) < 2:
        return None
    rows = [x[0] for x in per_book.values()]
    midpoint = [statistics.median(v[i] for v in rows) for i in range(3)]
    den = sum(midpoint)
    if den <= 0:
        return None
    probabilities = [round(v / den, 7) for v in midpoint]
    latest = max(x[1] for x in per_book.values())
    return {
        "source_event_id": event_id, "home": home, "away": away,
        "kickoff_utc": kickoff.isoformat(), "market_last_update_utc": latest.isoformat(),
        "contributing_bookmakers": len(per_book),
        "p_home": probabilities[0], "p_draw": probabilities[1], "p_away": probabilities[2],
        "probabilities_are_no_vig_consensus": True,
        "prediction_or_value_bet": False,
    }


def collect(key, *, opener=urlopen, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    checked = verify(key, opener=opener)
    q = checked["quota"]
    if not may_spend(q):
        return {"schema": "football-king-market-consensus-v1",
                "provider": "the-odds-api.com/v4",
                "status": "HOLD", "reason": "FREE_QUOTA_GUARD",
                "as_of_utc": now.isoformat(), "quota": q,
                "event_count": 0, "events": [], "leagues": [],
                "quota_policy": {"max_monthly_used": MAX_USED, "remaining_floor": MIN_REMAINING},
                "raw_bookmaker_quotes_redistributed": False,
                "market_probabilities_calibrated": False,
                "production_recommendations": "DISABLED"}
    events, results = [], []
    latest = q
    for league, sport in SPORTS.items():
        if not checked["supported"][league]:
            results.append({"league": league, "status": "NOT_AVAILABLE_ON_ACCOUNT",
                            "events": 0, "credits_charged": 0})
            continue
        if not checked["active"][league]:
            results.append({"league": league, "status": "INACTIVE", "events": 0, "credits_charged": 0})
            continue
        if not may_spend(latest):
            results.append({"league": league, "status": "QUOTA_GUARD", "events": 0, "credits_charged": 0})
            continue
        try:
            matches, latest = retrieve(
                "/sports/" + sport + "/odds/", key, opener=opener,
                params={"regions": "eu", "markets": "h2h",
                        "oddsFormat": "decimal", "dateFormat": "iso"})
            if not isinstance(matches, list):
                raise APIProblem("BAD_ODDS_SCHEMA")
            if latest.get("used") is None or latest.get("remaining") is None:
                # Provider did not return billable credit counters: stop further queries.
                results.append({"league": league, "status": "MISSING_QUOTA_HEADERS",
                                "events": 0, "credits_charged": None})
                break
            normalized = [aggregate(x, now=now) for x in matches[:500]]
            rows = [x for x in normalized if x is not None]
            for row in rows:
                row["league"] = league
            events.extend(rows)
            results.append({"league": league, "status": "READY_RESEARCH" if rows else "NO_COMPARABLE_3WAY_ODDS",
                            "events": len(rows), "credits_charged": latest.get("last")})
        except APIProblem as exc:
            results.append({"league": league, "status": "HOLD", "reason": str(exc),
                            "events": 0, "credits_charged": None})
            if str(exc) in ("KEY_REJECTED_OR_NOT_AUTHORIZED", "SPORT_OR_PLAN_NOT_AUTHORIZED",
                            "RATE_LIMITED", "MISSING_QUOTA_HEADERS", "PROVIDER_NETWORK_ERROR",
                            "PROVIDER_BAD_JSON"):
                break
    events.sort(key=lambda r: (r["kickoff_utc"], r["league"], r["source_event_id"]))
    return {
        "schema": "football-king-market-consensus-v1",
        "provider": "the-odds-api.com/v4", "as_of_utc": now.isoformat(),
        "status": "RESEARCH_ONLY" if events else "HOLD",
        "reason": None if events else "NO_VALID_3WAY_MARKET_SNAPSHOTS",
        "quota": latest, "market": "h2h", "region": "eu",
        "quota_policy": {"max_monthly_used": MAX_USED, "remaining_floor": MIN_REMAINING},
        "leagues": results, "event_count": len(events), "events": events,
        "raw_bookmaker_quotes_redistributed": False,
        "raw_bookmaker_names_redistributed": False,
        "market_probabilities_calibrated": False,
        "model_value_advantage_verified": False,
        "production_recommendations": "DISABLED",
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=("verify", "collect"), default="verify")
    p.add_argument("--output", default="market/latest.json")
    args = p.parse_args(argv)
    key = os.environ.get("THE_ODDS_API_KEY", "")
    try:
        if args.mode == "verify":
            result = verify(key)
            print(json.dumps({"connected": result["connected"], "provider": result["provider"],
                              "quota": result["quota"], "supported": result["supported"],
                              "active": result["active"],
                              "production_recommendations": "DISABLED"}, ensure_ascii=False))
        else:
            result = collect(key)
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"status": result["status"], "reason": result["reason"],
                              "event_count": result["event_count"],
                              "quota": result["quota"], "leagues": result["leagues"],
                              "production_recommendations": "DISABLED"}, ensure_ascii=False))
    except APIProblem as exc:
        # SAFE errors only, no user credentials or full URLs.
        print(json.dumps({"connected": False, "error_code": str(exc),
                          "production_recommendations": "DISABLED"}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
