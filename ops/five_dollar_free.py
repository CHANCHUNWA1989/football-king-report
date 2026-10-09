"""Optional $0 5DollarFootballAPI 1X2 availability probe (isolated research).

Uses at most three requests per run: account, scheduled fixtures, one fixture
1X2. Never saves source bookmaker quotes, actual price values, a fabricated
point-in-time timestamp or any production betting signal.
Official docs https://5dollarfootballapi.com/docs
"""
import argparse
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

ROOT = "https://api.5dollarfootballapi.com/v1"
MAX_CALLS = 3
MAX_RESPONSE = 1_000_000
LEAGUES = {
    "premier league": "epl", "la liga": "laliga",
    "bundesliga": "bundesliga", "serie a": "seriea", "ligue 1": "ligue1",
}
ATTRIBUTION = "Football data by 5DollarFootballAPI"
ATTRIBUTION_URL = "https://5dollarfootballapi.com/"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("UNTRUSTED_REDIRECT")


def stamp(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_PROVIDER_TIME")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("NAIVE_PROVIDER_TIME")
    return dt.astimezone(timezone.utc)


def parse_fixture_list(payload, now):
    if not isinstance(payload, dict) or payload.get("success") != 1:
        raise ValueError("UNAUTHORIZED_OR_UNKNOWN_FIXTURE_RESPONSE")
    entries = payload.get("data")
    if not isinstance(entries, list) or len(entries) > 100:
        raise ValueError("BAD_FIXTURE_LIST")
    candidates = []
    for row in entries:
        if not isinstance(row, dict) or row.get("status") != "scheduled":
            continue
        league = row.get("league")
        teams = row.get("teams")
        if not isinstance(league, dict) or not isinstance(teams, dict):
            continue
        league_code = LEAGUES.get(str(league.get("name", "")).strip().lower())
        if not league_code:
            continue
        home, away = teams.get("home"), teams.get("away")
        if not isinstance(home, dict) or not isinstance(away, dict):
            continue
        if not all(isinstance(x.get("name"), str) and x["name"].strip()
                   for x in (home, away)) or home["name"] == away["name"]:
            continue
        ident = row.get("id")
        if type(ident) is not int or ident <= 0:
            continue
        try:
            kickoff = stamp(row.get("kickoff_utc"))
        except (TypeError, ValueError, OverflowError):
            continue
        if not now + timedelta(minutes=30) < kickoff <= now + timedelta(days=7):
            continue
        candidates.append({"id": ident, "league": league_code,
                           "kickoff_utc": kickoff.isoformat()})
    # Never store or publish raw fixture rows or infer all-league coverage.
    return candidates


def valid_three_way(payload, selected_fixture):
    if (not isinstance(payload, dict) or payload.get("success") != 1
            or not isinstance(payload.get("data"), dict)):
        return False
    data = payload["data"]
    if data.get("fixture_id") != selected_fixture or not isinstance(data.get("bookmakers"), list):
        return False
    # Free key only includes the Bet365 book. Other bookmaker entries are
    # outside the free-tier entitlement and must not be treated as covered.
    books = [x for x in data["bookmakers"] if isinstance(x, dict) and x.get("slug") == "bet365"]
    if len(books) != 1:
        return False
    markets = books[0].get("odds")
    if not isinstance(markets, dict):
        return False
    h2h = markets.get("1x2")
    if not isinstance(h2h, dict):
        return False
    # Opening/closing are NOT point-in-time offers. Never promote these to
    # the primary prediction market, EV, ROI or executable odds.
    opening = h2h.get("opening")
    if not isinstance(opening, dict):
        return False
    values = [opening.get(n) for n in ("home", "draw", "away")]
    if not all(type(v) in (int, float) and math.isfinite(v)
               and 1.01 <= v <= 500 for v in values):
        return False
    return .98 <= sum(1 / v for v in values) <= 1.35


def fetch(path, key, requester=None):
    if not key or not path.startswith("/") or "?" in path and "api" in path:
        raise ValueError("DISALLOWED_REQUEST")
    if not (path == "/status" or path.startswith("/fixtures")):
        raise ValueError("OUTSIDE_FREE_ENDPOINTS")
    req = Request(ROOT + path, headers={
        "Authorization": "Bearer " + key,
        "Accept": "application/json",
        "User-Agent": "FootballKingFreeResearch/1.0",
    })
    opener = requester or build_opener(NoRedirect()).open
    try:
        with opener(req, timeout=12) as response:
            raw = response.read(MAX_RESPONSE + 1)
            remaining = response.headers.get("X-RateLimit-Remaining") if hasattr(response, "headers") else None
        if len(raw) > MAX_RESPONSE:
            return None, "RESPONSE_TOO_LARGE", None
        doc = json.loads(raw.decode("utf-8"))
        if not isinstance(doc, dict) or doc.get("success") != 1:
            return None, "BAD_OR_UNAUTHORIZED_RESPONSE", None
        try:
            remaining = int(remaining) if remaining is not None else None
        except (ValueError, TypeError):
            remaining = None
        return doc, "OK", remaining
    except HTTPError as exc:
        if exc.code in (401, 403):
            return None, "KEY_OR_FREE_PLAN_DENIED", None
        if exc.code == 429:
            return None, "QUOTA_EXHAUSTED", None
        return None, "PROVIDER_HTTP_ERROR", None
    except (URLError, TimeoutError, OSError):
        return None, "NETWORK_ERROR", None
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return None, "MALFORMED_PROVIDER_RESPONSE", None


def collect(*, key="", now=None, requester=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_CLOCK")
    report = {
        "schema": "football-king-five-dollar-free-probe-v1",
        "checked_utc": now.isoformat(), "provider": "5dollarfootballapi.com",
        "status": "NOT_CONFIGURED" if not key else "HOLD",
        "reason": "FREE_KEY_REQUIRED" if not key else "NO_VERIFIED_FREE_DATA",
        "configured": bool(key), "calls_attempted": 0, "maximum_calls": MAX_CALLS,
        "eligible_fixture_sample_count": 0, "one_book_1x2_sample_available": False,
        "source_is_bet365_only_on_free_plan": True,
        "fixture_sample_is_not_complete_league_coverage": True,
        "bookmaker_price_values_saved": False,
        "point_in_time_market_verified": False,
        "executable_quote_at_prediction_time_verified": False,
        "safe_primary_odds_fallback": False,
        "research_model_changed": False,
        "raw_source_payload_redistributed": False,
        "attribution": ATTRIBUTION, "attribution_url": ATTRIBUTION_URL,
        "production_recommendations": "DISABLED",
    }
    if not key:
        return report

    def query(path):
        if report["calls_attempted"] >= MAX_CALLS:
            raise ValueError("LOCAL_REQUEST_CAP")
        report["calls_attempted"] += 1
        return fetch(path, key, requester=requester)

    doc, why, remaining = query("/status")
    if why != "OK":
        report["reason"] = why
        return report
    status = doc.get("data")
    if not isinstance(status, dict) or status.get("plan") not in ("free", "community"):
        report["reason"] = "UNKNOWN_OR_NOT_FREE_PLAN"
        return report
    report["free_plan_verified"] = True
    if remaining is not None and remaining < 2:
        report["reason"] = "QUOTA_RESERVE"
        return report

    doc, why, remaining = query("/fixtures?"+urlencode({"status": "scheduled", "per_page": 50}))
    if why != "OK":
        report["reason"] = why
        return report
    try:
        candidates = parse_fixture_list(doc, now)
    except (ValueError, KeyError, TypeError):
        report["reason"] = "FIXTURE_SCHEMA_UNVERIFIED"
        return report
    report["eligible_fixture_sample_count"] = len(candidates)
    if not candidates:
        report["status"] = "PARTIAL"
        report["reason"] = "NO_TIME_ELIGIBLE_TOP5_FIXTURES_IN_SAMPLE"
        return report
    if remaining is not None and remaining < 1:
        report["status"] = "PARTIAL"
        report["reason"] = "QUOTA_RESERVE"
        return report
    # At most ONE pre-match fixture is probed. A single-book opening price
    # never substitutes for the existing multi-bookmaker consensus source.
    pick = min(candidates, key=lambda row: (row["kickoff_utc"], row["id"]))
    doc, why, _ = query(f"/fixtures/{pick['id']}/odds?market=1x2")
    if why != "OK":
        report["status"] = "PARTIAL"
        report["reason"] = why
        return report
    available = valid_three_way(doc, pick["id"])
    report["one_book_1x2_sample_available"] = available
    report["status"] = "PARTIAL"
    report["reason"] = "SINGLE_BOOK_UNTIMED_RESEARCH_ONLY" if available else "ONE_BOOK_SCHEMA_OR_PRICE_NOT_VERIFIED"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="five-dollar-probe.json")
    args = parser.parse_args(argv)
    result = collect(key=os.environ.get("FIVEDOLLAR_FOOTBALL_API_KEY", ""))
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "reason": result["reason"],
                      "calls_attempted": result["calls_attempted"],
                      "eligible_fixture_sample_count": result["eligible_fixture_sample_count"],
                      "one_book_1x2_sample_available": result["one_book_1x2_sample_available"],
                      "production_recommendations": "DISABLED"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
