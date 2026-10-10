"""Six-league free PropLine *coverage-only* sidecar and seven evidence gates.

Never persist individual odds, bookmaker identities, team rows, credentials or
provider raw responses. This is not an executable-odds or profitability feed.
Seven bounded calls at most per run (sports catalogue + 6 league odds).
"""
import argparse
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPRedirectHandler, build_opener

from asian_handicap_research import quarter_units
from team_identity import team_id

SCHEMA = "football-king-six-free-league-quality-v1"
AUDIT_SCHEMA = "football-king-seven-evidence-gates-v1"
ROOT = "https://api.prop-line.com/v1"
LICENSE = "https://prop-line.com/terms"
LEAGUES = {
    "epl": "soccer_epl",
    "championship": "soccer_efl_champ",
    "bundesliga": "soccer_germany_bundesliga",
    "laliga": "soccer_spain_la_liga",
    "seriea": "soccer_italy_serie_a",
    "ligue1": "soccer_france_ligue_one",
}
MAX_CALLS = 7
MAX_BYTES = 2_500_000
# Public filter from official docs; prevents oversized multi-book boards.
BOOK_FILTER = "&bookmakers=pinnacle,bovada,fanduel,draftkings"
CHAMP_KEYS = ("soccer_efl_champ", "soccer_efl_championship",
              "soccer_england_championship", "soccer_england_efl_championship")
MAX_EVENTS = 160
MAX_BOOKS = 70
MAX_AGE = timedelta(minutes=20)
STATUS = ("RESEARCH_ONLY", "HOLD", "NOT_CONFIGURED")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("UNTRUSTED_REDIRECT")


def utc(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_UTC")
    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return value.astimezone(timezone.utc)


def fetch(path, key):
    if not isinstance(key, str) or not key or path not in (
        "/sports", *(f"/sports/{sport}/odds?markets=h2h,spreads,totals{BOOK_FILTER}"
                     for sport in (*LEAGUES.values(), *CHAMP_KEYS))):
        raise ValueError("DISALLOWED_PROPLINE_REQUEST")
    request = Request(ROOT + path, headers={
        "X-API-Key": key, "Accept": "application/json",
        "User-Agent": "FootballKingSixLeagueFreeResearch/1.0"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=15) as response:
            raw = response.read(MAX_BYTES + 1)
            remaining = response.headers.get("X-Daily-Remaining")
        if len(raw) > MAX_BYTES:
            raise ValueError("PROVIDER_OVERSIZE")
        doc = json.loads(raw.decode("utf-8"))
        remaining = int(remaining) if remaining is not None else None
        if remaining is not None and remaining < 0:
            remaining = None
        return doc, remaining
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise ValueError("KEY_REJECTED_OR_SCOPE_DENIED") from None
        if exc.code in (402, 422):
            raise ValueError("PAID_SCOPE") from None
        if exc.code == 404:
            raise ValueError("LEAGUE_NOT_OFFERED") from None
        if exc.code == 429:
            raise ValueError("RATE_LIMITED") from None
        raise ValueError("PROVIDER_HTTP_FAILURE") from None
    except (URLError, OSError, TimeoutError):
        raise ValueError("NETWORK_FAILURE") from None
    except (UnicodeError, TypeError, json.JSONDecodeError):
        raise ValueError("UNEXPECTED_JSON") from None


def price(outcome):
    if not isinstance(outcome, dict):
        return False
    d = outcome.get("price_decimal")
    if type(d) in (int, float) and math.isfinite(d) and 1.01 <= d <= 100:
        return True
    a = outcome.get("price")
    return type(a) in (int, float) and math.isfinite(a) and (a <= -100 or a >= 100)


def side(outcome, home, away):
    if not isinstance(outcome, dict):
        return None
    flag = outcome.get("side")
    if flag in ("home", "away", "draw"):
        return flag
    name = outcome.get("name")
    return ("home" if name == home else "away" if name == away
            else "draw" if name == "Draw" else None)


def complete_market(market, home, away):
    """Return complete main-market type, or None. No half markets counted."""
    kind = market.get("key")
    if kind not in ("h2h", "spreads", "totals"):
        return None
    if market.get("period") not in (None, "full", "full_game", "ft"):
        return None
    if market.get("suspended_at") is not None:
        return None
    rows = market.get("outcomes")
    if not isinstance(rows, list) or len(rows) > 40:
        return None
    grouped = {}
    for outcome in rows:
        if not price(outcome):
            continue
        name = side(outcome, home, away) if kind != "totals" else outcome.get("name")
        point = outcome.get("point")
        if kind == "h2h":
            if name not in ("home", "away", "draw") or point is not None:
                continue
            key = (name, None)
        elif kind == "spreads":
            if name not in ("home", "away"):
                continue
            try:
                point = quarter_units(point)
            except (ValueError, TypeError):
                continue
            key = (name, point)
        else:
            if name not in ("Over", "Under"):
                continue
            try:
                point = quarter_units(point)
            except (ValueError, TypeError):
                continue
            if point < 0:
                continue
            key = (name, point)
        # Ambiguous duplicate outcomes invalidate this key; never first-wins.
        if key in grouped:
            grouped[key] = 2
        else:
            grouped[key] = 1
    if kind == "h2h":
        needed = {("home", None), ("draw", None), ("away", None)}
        return kind if set(grouped) == needed and all(x == 1 for x in grouped.values()) else None
    if kind == "spreads":
        return kind if any(
            grouped.get(("home", line)) == 1 and grouped.get(("away", -line)) == 1
            for s, line in grouped if s == "home") else None
    return kind if any(
        grouped.get(("Over", line)) == 1 and grouped.get(("Under", line)) == 1
        for s, line in grouped if s == "Over") else None


def extract(rows, league, sport, now):
    summary = dict(upcoming_events=0, utc_identity_events=0,
                   full_1x2_events=0, paired_spread_events=0,
                   paired_totals_events=0, stale_market_blocks=0,
                   duplicate_book_blocks=0, invalid_identity_events=0)
    if not isinstance(rows, list) or len(rows) > MAX_EVENTS:
        raise ValueError("UNSAFE_EVENTS_SHAPE")
    event_ids = set()
    for event in rows:
        if not isinstance(event, dict) or event.get("completed") is True or event.get("is_outright") is True:
            continue
        if event.get("sport_key") not in (None, sport):
            continue
        eid, home, away = event.get("id"), event.get("home_team"), event.get("away_team")
        if (type(eid) not in (str, int) or not str(eid)
                or not isinstance(home, str) or not isinstance(away, str)
                or not home or not away or home == away):
            summary["invalid_identity_events"] += 1
            continue
        try:
            kickoff = utc(event.get("commence_time"))
        except (TypeError, ValueError, OverflowError):
            summary["invalid_identity_events"] += 1
            continue
        if not now + timedelta(minutes=10) < kickoff <= now + timedelta(days=14):
            continue
        if str(eid) in event_ids:
            summary["invalid_identity_events"] += 1
            continue
        event_ids.add(str(eid))
        summary["upcoming_events"] += 1
        home_id, away_id = team_id(league, home), team_id(league, away)
        if not home_id or not away_id or home_id == away_id:
            summary["invalid_identity_events"] += 1
            continue
        summary["utc_identity_events"] += 1
        books = event.get("bookmakers")
        if not isinstance(books, list) or len(books) > MAX_BOOKS:
            continue
        per_kind = {"h2h": set(), "spreads": set(), "totals": set()}
        seen_books = set()
        for book in books:
            if not isinstance(book, dict) or not isinstance(book.get("key"), str) or not book["key"]:
                continue
            key = book["key"]
            if key in seen_books:
                summary["duplicate_book_blocks"] += 1
                # Don't allow duplicate blocks to increase distinct publisher count.
                for group in per_kind.values():
                    group.discard(key)
                continue
            seen_books.add(key)
            markets = book.get("markets")
            if not isinstance(markets, list) or len(markets) > 35:
                continue
            observed = set()
            for market in markets:
                if not isinstance(market, dict):
                    continue
                try:
                    age = now - utc(market.get("last_update"))
                except (ValueError, TypeError, OverflowError):
                    summary["stale_market_blocks"] += 1
                    continue
                if not -timedelta(seconds=5) <= age <= MAX_AGE:
                    summary["stale_market_blocks"] += 1
                    continue
                kind = complete_market(market, home, away)
                if kind is None:
                    continue
                if kind in observed:
                    per_kind[kind].discard(key)
                else:
                    per_kind[kind].add(key)
                    observed.add(kind)
        if len(per_kind["h2h"]) >= 2:
            summary["full_1x2_events"] += 1
        if per_kind["spreads"]:
            summary["paired_spread_events"] += 1
        if per_kind["totals"]:
            summary["paired_totals_events"] += 1
    return summary


def empty_league(league, configured):
    return {
        "league": league, "sport_key": LEAGUES[league],
        "status": "HOLD" if configured else "NOT_CONFIGURED",
        "reason": "PENDING_CHECK" if configured else "SET_PROPLINE_API_KEY",
        "requests_attempted": 0, "upcoming_events": 0, "utc_identity_events": 0,
        "full_1x2_events": 0, "paired_spread_events": 0,
        "paired_totals_events": 0, "stale_market_blocks": 0,
        "duplicate_book_blocks": 0, "invalid_identity_events": 0,
        "not_executable_odds": True,
    }


def collect(*, token=None, now=None, fetcher=fetch):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_CAPTURE")
    token = os.environ.get("PROPLINE_API_KEY", "") if token is None else token
    report = {
        "schema": SCHEMA, "captured_utc": now.isoformat(),
        "provider": "propline", "configured": bool(token),
        "status": "HOLD" if token else "NOT_CONFIGURED",
        "requests_attempted": 0, "max_requests": MAX_CALLS,
        "daily_remaining": None, "free_only": True,
        "license_reference": LICENSE,
        "coverage": [empty_league(l, bool(token)) for l in LEAGUES],
        "raw_bookmaker_quotes_published": False,
        "cross_provider_bookmaker_independence_verified": False,
        "out_of_sample_edge_verified": False,
        "automatic_model_change": False,
        "production_recommendations": "DISABLED",
    }
    if not token:
        return report
    try:
        catalogue, remaining = fetcher("/sports", token)
        report["requests_attempted"] += 1
        if not isinstance(catalogue, list):
            raise ValueError("INVALID_CATALOGUE")
        # Only exact England EFL Championship catalogue entries, no fuzzy competition inference.
        champ = [x.get("key") for x in catalogue if isinstance(x, dict)
                 and x.get("key") in CHAMP_KEYS and x.get("active") is not False]
        if len(champ) == 1:
            report["coverage"][1]["sport_key"] = champ[0]
        elif len(champ) > 1:
            # If exact alias exists, prefer it; otherwise avoid ambiguous provider IDs.
            report["coverage"][1]["sport_key"] = (
                "soccer_efl_champ" if "soccer_efl_champ" in champ else
                sorted(champ)[0])
        else:
            report["coverage"][1]["reason"] = "CHAMPIONSHIP_ABSENT_IN_PROVIDER_CATALOGUE"
        report["daily_remaining"] = remaining
    except (ValueError, TypeError) as exc:
        report["requests_attempted"] = max(report["requests_attempted"], 1)
        report["coverage"][0]["reason"] = "SPORTS_CATALOGUE_UNAVAILABLE"
        return report
    for row in report["coverage"]:
        if row["league"] == "championship" and row["reason"] == "CHAMPIONSHIP_ABSENT_IN_PROVIDER_CATALOGUE":
            continue
        if report["daily_remaining"] is not None and report["daily_remaining"] <= 75:
            row["reason"] = "QUOTA_RESERVE_75"
            continue
        report["requests_attempted"] += 1
        row["requests_attempted"] = 1
        if report["requests_attempted"] > MAX_CALLS:
            raise ValueError("MAX_CALLS_EXCEEDED")
        path = f'/sports/{row["sport_key"]}/odds?markets=h2h,spreads,totals{BOOK_FILTER}'
        try:
            events, remaining = fetcher(path, token)
            if remaining is not None:
                report["daily_remaining"] = remaining
            counts = extract(events, row["league"], row["sport_key"], now)
            row.update(counts)
            row["status"] = "RESEARCH_ONLY" if (
                counts["full_1x2_events"] or counts["paired_spread_events"] or
                counts["paired_totals_events"]) else "HOLD"
            row["reason"] = "QUALIFIED_MAIN_MARKET_OBSERVED" if row["status"] == "RESEARCH_ONLY" else "NO_COMPLETE_FRESH_PREMATCH_MARKET"
        except (TypeError, ValueError) as exc:
            # A status code or malformed feed never promotes a result.
            known = {"KEY_REJECTED_OR_SCOPE_DENIED", "PAID_SCOPE", "LEAGUE_NOT_OFFERED",
                     "RATE_LIMITED", "PROVIDER_HTTP_FAILURE", "NETWORK_FAILURE",
                     "UNEXPECTED_JSON", "PROVIDER_OVERSIZE", "UNSAFE_EVENTS_SHAPE"}
            row["reason"] = str(exc) if str(exc) in known else "UNVERIFIED_PROVIDER_FORMAT"
            if row["reason"] in ("RATE_LIMITED", "KEY_REJECTED_OR_SCOPE_DENIED"):
                break
    if any(x["status"] == "RESEARCH_ONLY" for x in report["coverage"]):
        report["status"] = "RESEARCH_ONLY"
    return report


def validate(report, *, now=None):
    now = now or datetime.now(timezone.utc)
    if (not isinstance(report, dict) or report.get("schema") != SCHEMA
            or report.get("provider") != "propline"
            or report.get("license_reference") != LICENSE
            or report.get("status") not in STATUS
            or report.get("free_only") is not True
            or report.get("max_requests") != MAX_CALLS
            or report.get("raw_bookmaker_quotes_published") is not False
            or report.get("cross_provider_bookmaker_independence_verified") is not False
            or report.get("out_of_sample_edge_verified") is not False
            or report.get("automatic_model_change") is not False
            or report.get("production_recommendations") != "DISABLED"
            or type(report.get("configured")) is not bool
            or type(report.get("requests_attempted")) is not int
            or not 0 <= report["requests_attempted"] <= MAX_CALLS):
        raise ValueError("INVALID_FREE_QUALITY_PROVENANCE")
    age = (now - utc(report["captured_utc"])).total_seconds()
    if not -300 <= age <= 48 * 3600:
        raise ValueError("STALE_OR_FUTURE_AUDIT")
    coverage = report.get("coverage")
    if (not isinstance(coverage, list) or len(coverage) != 6
            or [r.get("league") for r in coverage] != list(LEAGUES)):
        raise ValueError("INVALID_SIX_LEAGUE_COVERAGE")
    for item in coverage:
        if (item.get("sport_key") not in (
                    CHAMP_KEYS if item["league"] == "championship"
                    else (LEAGUES[item["league"]],))
                or item.get("status") not in STATUS
                or item.get("not_executable_odds") is not True
                or type(item.get("requests_attempted")) is not int
                or not 0 <= item["requests_attempted"] <= 1):
            raise ValueError("INVALID_LEAGUE_PROVENANCE")
        for key in ("upcoming_events", "utc_identity_events", "full_1x2_events",
                    "paired_spread_events", "paired_totals_events",
                    "duplicate_book_blocks", "stale_market_blocks",
                    "invalid_identity_events"):
            if type(item.get(key)) is not int or not 0 <= item[key] <= MAX_EVENTS * MAX_BOOKS * 36:
                raise ValueError("INVALID_COVERAGE_COUNTER")
        if any(item[k] > item["utc_identity_events"] for k in (
                "full_1x2_events", "paired_spread_events", "paired_totals_events")):
            raise ValueError("IMPOSSIBLE_QUALIFIED_COUNTS")
        if item["status"] == "RESEARCH_ONLY" and not any(item[k] for k in (
                "full_1x2_events", "paired_spread_events", "paired_totals_events")):
            raise ValueError("FALSE_POSITIVE_MARKET")
    if not report["configured"] and (report["requests_attempted"] or report["status"] != "NOT_CONFIGURED"):
        raise ValueError("UNCONFIGURED_KEY_USED")
    return True


def audit(six_report, market=None, sources=None, settled=None):
    """Seven explicit gates. A partial implementation is never 'passed'."""
    validate(six_report)
    result = {
        "schema": AUDIT_SCHEMA, "captured_utc": six_report["captured_utc"],
        "status": "HOLD", "checks": [], "passed": 0, "total": 7,
        "can_promote_model": False, "can_recommend_bets": False,
        "production_recommendations": "DISABLED",
    }
    def add(key, state, description):
        result["checks"].append({"key": key, "state": state, "evidence": description})
    market_rows = market.get("events", []) if isinstance(market, dict) else []
    league_counts = {l: 0 for l in LEAGUES}
    timely = 0
    for event in market_rows[:3000] if isinstance(market_rows, list) else []:
        if not isinstance(event, dict) or event.get("league") not in LEAGUES:
            continue
        try:
            kickoff, update = utc(event["kickoff_utc"]), utc(event["market_last_update_utc"])
            captured = utc(market["as_of_utc"])
            known = bool(team_id(event["league"], event.get("home"))
                         and team_id(event["league"], event.get("away")))
            if update <= captured < kickoff - timedelta(minutes=10) and known:
                league_counts[event["league"]] += 1
                timely += 1
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    distinct_market_leagues = sum(n > 0 for n in league_counts.values())
    add("utc_fixture_identity",
        "PARTIAL" if distinct_market_leagues == 6 else "HOLD",
        f"{distinct_market_leagues}/6 market leagues with time-valid identified samples; per-fixture second-publisher verification missing")
    has_source_clock = isinstance(sources, dict) and isinstance(sources.get("collected_utc"), str)
    add("source_time_quota_licence",
        "PARTIAL" if (six_report["configured"] and has_source_clock and six_report["requests_attempted"] > 0) else "HOLD",
        "source time and quota tracked, vendor policy referenced; per-row licensed data retention not proven")
    spread = sum(x["paired_spread_events"] for x in six_report["coverage"])
    total = sum(x["paired_totals_events"] for x in six_report["coverage"])
    complete = sum(x["paired_spread_events"] > 0 and x["paired_totals_events"] > 0
                   for x in six_report["coverage"])
    add("paired_asian_totals",
        "PASS" if complete == 6 else "PARTIAL" if spread or total else "HOLD",
        f"{complete}/6 leagues have full two-sided handicap AND total; complete spread {spread}, total {total} fixture observations")
    add("bookmaker_cross_feed_dedupe", "PARTIAL" if spread or total else "HOLD",
        "same-feed duplicate bookmaker blocks rejected; upstream cross-API bookmaker equivalence not independently verified")
    add("sealed_point_in_time",
        "PARTIAL" if distinct_market_leagues == 6 and timely == len(market_rows) else "HOLD",
        f"{timely}/{len(market_rows) if isinstance(market_rows,list) else 0} market observations pass sealed timestamp ordering; archived forward gate exists")
    n = (settled.get("n") if isinstance(settled, dict) and
         settled.get("production_recommendations") == "DISABLED" else None)
    add("out_of_sample_calibration",
        "HOLD", f"independent 300+ settled samples and Brier/Log Loss model-minus-market delta not yet certified; settled n={n if type(n) is int else 'unverified'}")
    add("model_promotion_safety",
        "PASS", "research-only independent sidecar; production recommendations disabled, no promotion access")
    result["passed"] = sum(x["state"] == "PASS" for x in result["checks"])
    result["partial"] = sum(x["state"] == "PARTIAL" for x in result["checks"])
    result["held"] = result["total"] - result["passed"] - result["partial"]
    return result


def load(path):
    try:
        p = Path(path)
        if not p.is_file() or p.stat().st_size > 3_000_000:
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=("collect", "validate", "audit"), required=True)
    p.add_argument("--input", default="six-free.json")
    p.add_argument("--output", default="six-free.json")
    p.add_argument("--market", default="market/latest.json")
    p.add_argument("--sources", default="sources/latest.json")
    p.add_argument("--settled", default="app/site/evidence.json")
    a = p.parse_args()
    if a.mode == "collect":
        doc = collect()
    else:
        doc = load(a.input)
        if a.mode == "validate":
            validate(doc)
            print(json.dumps({"valid": True, "status": doc["status"],
                              "requests_attempted": doc["requests_attempted"],
                              "production_recommendations": "DISABLED"}))
            return
        doc = audit(doc, load(a.market), load(a.sources), load(a.settled))
    Path(a.output).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    print(json.dumps({"schema": doc["schema"], "status": doc["status"],
                      "requests_attempted": doc.get("requests_attempted", 0),
                      "passed": doc.get("passed", 0),
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
