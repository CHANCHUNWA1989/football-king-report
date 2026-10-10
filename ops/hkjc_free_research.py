"""Optional FREE Tipsme HKJC football market availability audit.

Tipsme is NOT the Hong Kong Jockey Club. No official HKJC public API
credentials, access to betting accounts, scraping or bet placement.

API provider: https://tipsme.hk/zh-HK/developers/docs/odds
Free tier: https://tipsme.hk/zh-HK/developers/pricing
Bounded to 2 bonus schedule calls + 4 HKJC match quote calls/day.
Never persist match IDs, team names, raw odds or original provider payloads.
"""
import argparse
import json
import math
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPRedirectHandler, build_opener
from zoneinfo import ZoneInfo

SCHEMA = "football-king-hkjc-tipsme-free-research-v1"
BASE = "https://api.tipsme.hk/v1/football"
MAX_CALLS = 6
MAX_QUOTE_CALLS = 4
MAX_RESPONSE_BYTES = 1_200_000
MIN_QUOTA_REMAINING = 7
MAX_AGE = timedelta(minutes=20)
HK = ZoneInfo("Asia/Hong_Kong")
# Do not infer exact six-league identity from generic 'Premier League'.
COMPETITIONS = {
    "English Premier League": "epl",
    "Premier League (England)": "epl",
    "English Championship": "championship",
    "EFL Championship": "championship",
    "German Bundesliga": "bundesliga",
    "Bundesliga (Germany)": "bundesliga",
    "Spanish La Liga": "laliga",
    "La Liga (Spain)": "laliga",
    "Italian Serie A": "seriea",
    "Serie A (Italy)": "seriea",
    "French Ligue 1": "ligue1",
    "Ligue 1 (France)": "ligue1",
    "Japanese Division 1": "japan_j1",
    "Japan J1 League": "japan_j1",
    "J1 League": "japan_j1",
    "日本職業聯賽": "japan_j1",
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("REDIRECT_NOT_TRUSTED")


def utc(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_TIME")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("NAIVE_TIME")
    return dt.astimezone(timezone.utc)


def request(path, key):
    if not isinstance(key, str) or not key:
        raise ValueError("MISSING_AUTH")
    if path not in (
        "/matches?date=",  # dummy sentinel intentionally not callable
    ) and not (path.startswith("/matches?date=") or
               path.startswith("/matches/") and path.endswith("/odds/hkjc")):
        raise ValueError("PATH_NOT_ALLOWED")
    # Validate path values to disallow untrusted URL payloads.
    if path.startswith("/matches?date="):
        import re
        if not re.fullmatch(r"/matches\?date=20[0-9]{2}-[0-9]{2}-[0-9]{2}&tz=480&page=1&pageSize=100", path):
            raise ValueError("BAD_SCHEDULE_PATH")
    else:
        ident = path[len("/matches/"):-len("/odds/hkjc")]
        if not ident.isascii() or not ident.isdecimal() or not (0 < int(ident) < 2**31):
            raise ValueError("BAD_MATCH_ID")
    req = Request(BASE + path, headers={
        "Authorization": "Bearer " + key, "Accept": "application/json",
        "User-Agent": "FootballKingHkjcResearch/1.0"})
    try:
        with build_opener(NoRedirect()).open(req, timeout=12) as resp:
            raw = resp.read(MAX_RESPONSE_BYTES + 1)
            remaining = resp.headers.get("X-Quota-Remaining")
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("PROVIDER_OVERSIZE")
        blob = json.loads(raw.decode("utf-8"))
        quota = int(remaining) if remaining is not None else None
        if quota is not None and quota < 0:
            quota = None
        return blob, quota
    except HTTPError as exc:
        errors = {401:"AUTH_REJECTED", 403:"FREE_SCOPE_DENIED_OR_AUTH_REJECTED",
                  404:"NO_HKJC_BOARD", 429:"RATE_LIMITED",
                  502:"UPSTREAM_FAILURE",503:"UPSTREAM_FAILURE"}
        raise ValueError(errors.get(exc.code, "UPSTREAM_HTTP_FAILURE")) from None
    except (URLError, OSError, TimeoutError):
        raise ValueError("NETWORK_FAILURE") from None
    except (UnicodeError, json.JSONDecodeError, TypeError):
        raise ValueError("BAD_JSON") from None


def price(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return False
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return False
    return number.is_finite() and Decimal("1.01") <= number <= Decimal("100")


def point(value, *, maximum=8):
    if not isinstance(value, (str, int, float, Decimal)) or isinstance(value, bool):
        return None
    string = str(value).strip()
    if not string:
        return None
    sign = -1 if string.startswith("-") else 1
    try:
        pieces = string.lstrip("+-").split("/")
        if not 1 <= len(pieces) <= 2:
            return None
        nums = [Decimal(p.lstrip("+-")) for p in pieces]
        n = sign * sum(nums) / len(nums)
    except (InvalidOperation, ZeroDivisionError, TypeError):
        return None
    if not n.is_finite() or abs(n) > maximum or n * 4 != (n * 4).to_integral_value():
        return None
    return n


def recent(row, now, kickoff):
    try:
        observed = utc(row.get("recordedUtc"))
    except (ValueError, TypeError, OverflowError):
        return False
    return -timedelta(seconds=5) <= now-observed <= MAX_AGE and observed < kickoff


def full_market_counts(board, now, kickoff):
    """Only count simultaneous two-sided, fresh, correctly signed markets."""
    counts = {"had": False, "handicap": False, "goals": False, "corners": False}
    if not isinstance(board, dict):
        return counts
    doc = board.get("data", board)
    if not isinstance(doc, dict):
        return counts
    types = (
        ("matchResult", "had"),
        ("handicap", "handicap"),
        ("overUnder", "goals"),
        ("cornersOverUnder", "corners"),
    )
    for field, market in types:
        rows = doc.get(field)
        if not isinstance(rows, list) or len(rows) > 40:
            continue
        for row in rows:
            if not isinstance(row, dict) or not recent(row, now, kickoff):
                continue
            if market == "had":
                valid = all(price(row.get(k)) for k in ("home", "draw", "away"))
            elif market == "handicap":
                h = point(row.get("homeLine"))
                a = point(row.get("awayLine"))
                valid = (h is not None and a is not None and h == -a
                         and price(row.get("home")) and price(row.get("away")))
            else:
                pt = point(row.get("line"), maximum=(30 if market == "corners" else 8))
                valid = pt is not None and pt >= 0 and price(row.get("over")) and price(row.get("under"))
            if valid:
                counts[market] = True
                break
    return counts


def fixtures(doc, *, now):
    rows = doc.get("data") if isinstance(doc, dict) else None
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValueError("INVALID_SCHEDULE_RESPONSE")
    accepted = []
    for row in rows:
        if not isinstance(row, dict) or row.get("isHkjc") is not True:
            continue
        if row.get("status") != "scheduled":
            continue
        eid, home, away, league_obj = (row.get("id"), row.get("home"),
                                       row.get("away"), row.get("competition"))
        if (type(eid) is not int or not 0 < eid < 2**31
                or not isinstance(home, dict) or not isinstance(away, dict)
                or not isinstance(league_obj, dict)):
            continue
        names = [home.get("nameOriginal") or home.get("name"),
                 away.get("nameOriginal") or away.get("name")]
        if not all(isinstance(n, str) and n.strip() for n in names) or names[0] == names[1]:
            continue
        names_comp = [league_obj.get("nameOriginal"), league_obj.get("name")]
        mapped = {COMPETITIONS.get(x) for x in names_comp if isinstance(x, str)}
        mapped.discard(None)
        if len(mapped) != 1:
            continue
        league = mapped.pop()
        try:
            ko = utc(row["kickoffUtc"])
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
        if now + timedelta(minutes=10) < ko <= now + timedelta(hours=32):
            accepted.append((ko, eid, league))
    return accepted


def collect(*, key=None, now=None, fetcher=request):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_CAPTURE")
    key = os.environ.get("TIPSME_API_KEY", "") if key is None else key
    rep = {
        "schema":SCHEMA, "captured_utc":now.isoformat(),
        "provider":"tipsme_hkjc_third_party",
        "not_direct_hkjc_official_api":True,
        "status":"NOT_CONFIGURED" if not key else "HOLD",
        "reason":"SET_TIPSME_API_KEY" if not key else "NO_ELIGIBLE_HKJC_BOARD",
        "configured":bool(key), "requests_attempted":0,
        "max_requests":MAX_CALLS, "free_only":True,
        "quota_remaining":None, "upcoming_hkjc_fixtures_identified":0,
        "hkjc_boards_checked":0, "fresh_had_events":0,
        "fresh_handicap_events":0, "fresh_totals_events":0,
        "fresh_corners_events":0,
        "coverage_by_league":{x:0 for x in (*sorted(set(COMPETITIONS.values())),)},
        "source":"https://tipsme.hk/zh-HK/developers/docs/odds",
        "external_license_redistribution_verified":False,
        "raw_quotes_published":False, "bookmaker_names_published":False,
        "independent_market_model_calibrated":False,
        "not_executable_odds":True, "not_hkjc_account_connected":True,
        "can_execute_bet":False, "automatic_model_change":False,
        "production_recommendations":"DISABLED",
    }
    if not key:
        return rep
    scanned = []
    for day in (now.astimezone(HK).date(),
                (now + timedelta(days=1)).astimezone(HK).date()):
        path = f"/matches?date={day.isoformat()}&tz=480&page=1&pageSize=100"
        try:
            data, rem = fetcher(path, key)
            rep["requests_attempted"] += 1
            if rem is not None:
                rep["quota_remaining"] = rem
            scanned.extend(fixtures(data, now=now))
        except (TypeError, ValueError) as exc:
            rep["requests_attempted"] += 1
            rep["reason"] = "SCHEDULE_LOOKUP_FAILED"
            if str(exc) in ("FREE_SCOPE_DENIED_OR_AUTH_REJECTED", "AUTH_REJECTED", "RATE_LIMITED"):
                break
    distinct = {}
    for ko, eid, league in sorted(scanned):
        if eid in distinct:
            continue
        distinct[eid] = (ko, league)
    rep["upcoming_hkjc_fixtures_identified"] = len(distinct)
    for eid, (ko, league) in list(distinct.items())[:MAX_QUOTE_CALLS]:
        if rep["quota_remaining"] is not None and rep["quota_remaining"] <= MIN_QUOTA_REMAINING:
            rep["reason"] = "FREE_DAILY_QUOTA_RESERVE"
            break
        if rep["requests_attempted"] >= MAX_CALLS:
            break
        try:
            data, rem = fetcher(f"/matches/{eid}/odds/hkjc", key)
            rep["requests_attempted"] += 1
            if rem is not None:
                rep["quota_remaining"] = rem
            fields = full_market_counts(data, now, ko)
            rep["hkjc_boards_checked"] += 1
            if any(fields.values()):
                rep["coverage_by_league"][league] += 1
                for key_name,target in (
                    ("had","fresh_had_events"),("handicap","fresh_handicap_events"),
                    ("goals","fresh_totals_events"),("corners","fresh_corners_events")):
                    if fields[key_name]:
                        rep[target] += 1
        except (TypeError, ValueError) as exc:
            rep["requests_attempted"] += 1
            if str(exc) in ("FREE_SCOPE_DENIED_OR_AUTH_REJECTED", "AUTH_REJECTED", "RATE_LIMITED"):
                rep["reason"] = str(exc)
                break
            continue
    if any(rep[k] for k in ("fresh_had_events","fresh_handicap_events",
                            "fresh_totals_events","fresh_corners_events")):
        rep["status"] = "RESEARCH_ONLY"
        rep["reason"] = "FRESH_READ_ONLY_THIRD_PARTY_HKJC_RESEARCH"
    return rep


def validate(rep):
    if (not isinstance(rep, dict) or rep.get("schema") != SCHEMA
            or rep.get("provider") != "tipsme_hkjc_third_party"
            or rep.get("status") not in ("NOT_CONFIGURED", "HOLD", "RESEARCH_ONLY")
            or rep.get("not_direct_hkjc_official_api") is not True
            or rep.get("free_only") is not True or rep.get("max_requests") != MAX_CALLS
            or rep.get("external_license_redistribution_verified") is not False
            or rep.get("raw_quotes_published") is not False
            or rep.get("bookmaker_names_published") is not False
            or rep.get("independent_market_model_calibrated") is not False
            or rep.get("not_executable_odds") is not True
            or rep.get("not_hkjc_account_connected") is not True
            or rep.get("can_execute_bet") is not False
            or rep.get("automatic_model_change") is not False
            or rep.get("production_recommendations") != "DISABLED"):
        raise ValueError("INVALID_HKJC_RESEARCH_PROVENANCE")
    if (type(rep.get("requests_attempted")) is not int
            or not 0 <= rep["requests_attempted"] <= MAX_CALLS):
        raise ValueError("INVALID_REQUEST_BUDGET")
    for name in ("upcoming_hkjc_fixtures_identified","hkjc_boards_checked",
                 "fresh_had_events","fresh_handicap_events",
                 "fresh_totals_events","fresh_corners_events"):
        if type(rep.get(name)) is not int or rep[name] < 0:
            raise ValueError("INVALID_EVENT_COUNT")
    if (rep["hkjc_boards_checked"] > MAX_QUOTE_CALLS or
        any(rep[x] > rep["hkjc_boards_checked"] for x in
            ("fresh_had_events","fresh_handicap_events",
             "fresh_totals_events","fresh_corners_events"))):
        raise ValueError("IMPOSSIBLE_HKJC_COVERAGE")
    if (not isinstance(rep.get("coverage_by_league"), dict)
            or set(rep["coverage_by_league"]) != set(COMPETITIONS.values())
            or any(type(n) is not int or n < 0 or n > MAX_QUOTE_CALLS
                   for n in rep["coverage_by_league"].values())):
        raise ValueError("INVALID_LEAGUE_COVERAGE")
    if not rep.get("configured") and (rep["requests_attempted"] or rep["status"] != "NOT_CONFIGURED"):
        raise ValueError("UNCONFIGURED_CALLS")
    utc(rep.get("captured_utc"))
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="hkjc-free-research.json")
    a = p.parse_args()
    report = collect()
    validate(report)
    Path(a.output).write_text(
        json.dumps(report, ensure_ascii=False, indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":report["status"],"reason":report["reason"],
        "requests_attempted":report["requests_attempted"],
        "boards":report["hkjc_boards_checked"],
        "production_recommendations":"DISABLED",
    }))


if __name__=="__main__":
    main()
