"""Build actual worldwide research inputs from independently captured free feeds.

No catalogue entry is itself a fixture. OpenFootball scores are UNVERIFIED
training observations only. A model fixture needs two differently attributed
publishers agreeing on both clubs and exact timezone-aware kickoff.

Never infer UTC from date-only OpenFootball fields; never ingest odds, xG or
results from future fixtures. A missing/failed provider produces diagnostics
rather than a fabricated forecast. Requests are bounded and read-only.
"""
import argparse
import json
import os
import re
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from global_league_catalog import SCHEMA as CATALOG_SCHEMA
from global_league_catalog import SIX
from team_identity import team_id
from worldwide_shadow import SCHEMA as INPUT_SCHEMA
from worldwide_shadow import utc as parse_utc

OPENFOOTBALL = "https://raw.githubusercontent.com/openfootball/football.json/master/"
SPORTSDB = "https://www.thesportsdb.com/api/v1/json/123/eventsnextleague.php?id="
SPORTSDB_DAY = "https://www.thesportsdb.com/api/v1/json/123/eventsday.php?"
OPENLIGA = "https://api.openligadb.de/getmatchdata/"
MAX_LEAGUES_PER_RUN = 12
MAX_CALLS = 32
MAX_ELAPSED_SECONDS = 95
MAX_RESPONSE = 1_150_000
MAX_SNAPSHOT = 1_900_000
MAX_HISTORY_PER_LEAGUE = 1100
MAX_FIXTURES_PER_LEAGUE = 70
SCHEMA = "football-king-worldwide-source-build-status-v1"
ALLOWED_PATH = re.compile(r"^(?:20[0-9]{2}|20[0-9]{2}-[0-9]{2})/[a-z0-9][a-z0-9._-]{1,39}\.json$")
ALLOWED_LEAGUE = re.compile(r"^[a-z][a-z0-9_]{1,47}$")
GERMAN = {"bundesliga2": "bl2", "germany_liga3": "bl3"}
JAPAN_PRIORITY = ("japan_j1",)  # Small fixed quota: always audit J1, never auto-bet.
FOOTBALL_ONLY = {"SCHEDULED", "FINISHED"}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("UNEXPECTED_PROVIDER_REDIRECT")


def get_json(url):
    if not (url.startswith(OPENFOOTBALL) or url.startswith(SPORTSDB)
            or url.startswith(SPORTSDB_DAY) or url.startswith(OPENLIGA)):
        raise ValueError("DISALLOWED_WORLD_PROVIDER")
    if url.startswith(SPORTSDB) or url.startswith(SPORTSDB_DAY):
        ledger = (os.environ.get("FOOTBALL_KING_SPORTSDB_LEDGER")
                      or (os.path.join(os.environ["RUNNER_TEMP"], "sportsdb-budget.json")
                          if os.environ.get("RUNNER_TEMP") else None))
        if ledger:
            from free_api_rate_limit import reserve
            reserve(ledger)
    opener = build_opener(NoRedirect())
    request = Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "FootballKingWorldShadowData/1.0"})
    with opener.open(request, timeout=9) as response:
        raw = response.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise ValueError("SOURCE_RESPONSE_TOO_LARGE")
    return json.loads(raw.decode("utf-8"))


def safe_json(path):
    try:
        path = Path(path)
        if path.stat().st_size > MAX_SNAPSHOT:
            return None
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else None
    except (OSError, ValueError, UnicodeError):
        return None


def timestamp(v):
    if not isinstance(v, str):
        raise ValueError("NO_CAPTURE_CLOCK")
    return parse_utc(v)


def clock_ok(v, now, hours=16):
    try:
        age = now - timestamp(v)
        return timedelta(minutes=-5) <= age <= timedelta(hours=hours)
    except (ValueError, TypeError, OverflowError):
        return False


def historical(doc, *, now, source_path):
    if not isinstance(doc, dict) or not isinstance(doc.get("matches"), list):
        raise ValueError("INVALID_OPENFOOTBALL_HISTORY")
    if len(doc["matches"]) > 1600:
        raise ValueError("OVERLARGE_OPENFOOTBALL_HISTORY")
    cutoff = now.astimezone(timezone(timedelta(hours=8))).date()
    rows, seen = [], set()
    for item in doc["matches"]:
        if not isinstance(item, dict):
            continue
        home, away = item.get("team1"), item.get("team2")
        if not all(isinstance(x, str) and 1 <= len(x) <= 100 for x in (home, away)):
            continue
        score = item.get("score")
        ft = score.get("ft") if isinstance(score, dict) else None
        if (not isinstance(ft, list) or len(ft) != 2
                or not all(type(x) is int and 0 <= x <= 20 for x in ft)):
            continue
        try:
            day = date.fromisoformat(item["date"])
        except (KeyError, ValueError, TypeError):
            continue
        if day >= cutoff:
            continue
        identity = (day.isoformat(), home, away)
        if identity in seen:
            continue
        seen.add(identity)
        rows.append({"home": home, "away": away, "date": day.isoformat(),
                     "status": "FINISHED", "score_ft": list(ft),
                     "result_source": "openfootball_json"})
    rows.sort(key=lambda x: (x["date"], x["home"], x["away"]))
    return rows[-MAX_HISTORY_PER_LEAGUE:]


def sportsdb_events(doc, league_id, now):
    if not isinstance(doc, dict) or not isinstance(doc.get("events"), list):
        return []
    events = []
    for item in doc["events"][:40]:
        if not isinstance(item, dict) or str(item.get("idLeague")) != str(league_id):
            continue
        if (item.get("intHomeScore") is not None
                or item.get("intAwayScore") is not None
                or str(item.get("strStatus", "")).lower() in
                    ("ft", "finished", "match finished")):
            continue
        home, away, event_id = (item.get("strHomeTeam"),
                                item.get("strAwayTeam"), item.get("idEvent"))
        if (not all(isinstance(x, str) and 1 <= len(x) <= 100 for x in (home, away))
                or not isinstance(event_id, (str, int)) or not str(event_id)):
            continue
        raw = item.get("strTimestamp")
        try:
            # TheSportsDB's strTimestamp represents UTC, even when no offset
            # is encoded. This exception applies ONLY to this publisher.
            if isinstance(raw, str) and "T" in raw:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                ko = parsed.astimezone(timezone.utc)
            else:
                continue
        except (ValueError, TypeError, OverflowError):
            continue
        if not now + timedelta(hours=1) <= ko <= now + timedelta(days=7):
            continue
        events.append({"provider": "thesportsdb",
                       "provider_event_id": str(event_id)[:80],
                       "home": home, "away": away,
                       "kickoff_utc": ko.isoformat(),
                       "captured_utc": now.isoformat(),
                       "status": "SCHEDULED", "score_ft": None})
    return events[:MAX_FIXTURES_PER_LEAGUE]


def openliga_events(doc, now):
    if not isinstance(doc, list) or len(doc) > 1100:
        return []
    events = []
    for item in doc:
        if not isinstance(item, dict) or item.get("matchIsFinished") is True:
            continue
        try:
            ko = timestamp(item["matchDateTimeUTC"])
            home = item["team1"]["teamName"]
            away = item["team2"]["teamName"]
            ident = item["matchID"]
            if not all(isinstance(x, str) and 1 <= len(x) <= 100 for x in (home, away)):
                continue
            if not now + timedelta(hours=1) <= ko <= now + timedelta(days=7):
                continue
            if not isinstance(ident, (str, int)):
                continue
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        events.append({"provider": "openligadb",
                       "provider_event_id": str(ident)[:80],
                       "home": home, "away": away,
                       "kickoff_utc": ko.isoformat(),
                       "captured_utc": now.isoformat(),
                       "status": "SCHEDULED", "score_ft": None})
    return events[:MAX_FIXTURES_PER_LEAGUE]


def openliga_history(doc, now):
    """German community score results, strictly finished FT only.

    This source does not independently attest the final result and cannot
    validate ROI. It simply supplies additional labelled Shadow-only training.
    """
    if not isinstance(doc, list) or len(doc) > 1100:
        return []
    today = now.astimezone(ZoneInfo("Asia/Hong_Kong")).date()
    records, seen = [], set()
    for item in doc:
        if not isinstance(item, dict) or item.get("matchIsFinished") is not True:
            continue
        try:
            ko = timestamp(item["matchDateTimeUTC"])
            if ko.astimezone(ZoneInfo("Asia/Hong_Kong")).date() >= today:
                continue
            home, away = item["team1"]["teamName"], item["team2"]["teamName"]
            if not all(isinstance(x, str) and 1 <= len(x) <= 100 for x in (home, away)):
                continue
            results = item["matchResults"]
            if not isinstance(results, list):
                continue
            ft = [r for r in results if isinstance(r, dict)
                  and r.get("resultTypeID") == 2
                  and type(r.get("pointsTeam1")) is int
                  and type(r.get("pointsTeam2")) is int
                  and 0 <= r["pointsTeam1"] <= 20
                  and 0 <= r["pointsTeam2"] <= 20]
            if len(ft) != 1:
                continue
            identity = (ko.date().isoformat(), home, away)
            if identity in seen:
                continue
            seen.add(identity)
            records.append({
                "home": home, "away": away,
                "date": ko.astimezone(ZoneInfo("Asia/Hong_Kong")).date().isoformat(),
                "status": "FINISHED",
                "score_ft": [ft[0]["pointsTeam1"], ft[0]["pointsTeam2"]],
                "result_source": "openligadb_results",
            })
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    records.sort(key=lambda x: (x["date"], x["home"], x["away"]))
    return records[-MAX_HISTORY_PER_LEAGUE:]


def market_events(doc, league, now):
    # Read only fixture identifiers and times, NEVER derived probabilities or
    # raw prices. Missing/stale no-vig snapshot simply provides zero samples.
    if (not isinstance(doc, dict) or doc.get("status") != "RESEARCH_ONLY"
            or doc.get("production_recommendations") != "DISABLED"
            or not clock_ok(doc.get("as_of_utc"), now, 16)
            or not isinstance(doc.get("events"), list)):
        return []
    snap = timestamp(doc["as_of_utc"])
    rows = []
    for item in doc["events"][:300]:
        if not isinstance(item, dict) or item.get("league") != league:
            continue
        home, away = item.get("home"), item.get("away")
        if not all(isinstance(x, str) and 1 <= len(x) <= 100 for x in (home, away)):
            continue
        try:
            kickoff = timestamp(item["kickoff_utc"])
            last = timestamp(item["market_last_update_utc"])
            if not (last <= snap <= now + timedelta(minutes=5)
                    and now + timedelta(hours=1) <= kickoff <= now + timedelta(days=7)):
                continue
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
        ident = item.get("source_event_id")
        if not isinstance(ident, str) or not ident:
            continue
        rows.append({"provider": "the_odds_api_fixture",
                     "provider_event_id": ident[:80],
                     "home": home, "away": away,
                     "kickoff_utc": kickoff.isoformat(),
                     "captured_utc": snap.isoformat(),
                     "status": "SCHEDULED", "score_ft": None})
    return rows[:MAX_FIXTURES_PER_LEAGUE]


def count_pairs(observations, league, history):
    appeared = set()
    for row in history:
        appeared.add(team_id(league, row["home"]))
        appeared.add(team_id(league, row["away"]))
    by_pair = defaultdict(lambda: defaultdict(list))
    for item in observations:
        h = team_id(league, item["home"])
        a = team_id(league, item["away"])
        if not h or not a or h == a or h not in appeared or a not in appeared:
            continue
        by_pair[(h, a)][item["provider"]].append(item)
    good = 0
    for sources in by_pair.values():
        # An ambiguous double booking cannot count as independently
        # corroborated merely because the final duplicate overwrote another.
        if len(sources) < 2 or any(len(items) != 1 for items in sources.values()):
            continue
        times = [timestamp(items[0]["kickoff_utc"]) for items in sources.values()]
        if max(times) - min(times) <= timedelta(minutes=1):
            good += 1
    return good


def build(catalog, market, *, wide=None, now=None, loader=None, max_leagues=MAX_LEAGUES_PER_RUN):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    input_doc = {"schema": INPUT_SCHEMA, "collected_utc": now.isoformat(),
                 "production_recommendations": "DISABLED", "leagues": []}
    status = {"schema": SCHEMA, "collected_utc": now.isoformat(),
              "status": "HOLD", "reason": "NO_QUALIFIED_WORLDWIDE_INPUT",
              "eligible_catalogue_leagues": 0, "requested_leagues": 0,
              "historical_games": 0, "source_scheduled_fixtures": 0,
              "two_source_schedule_agreements": 0,
              "request_count": 0, "request_budget": MAX_CALLS,
              "production_recommendations": "DISABLED", "leagues": []}
    if (not isinstance(catalog, dict)
            or catalog.get("schema") != CATALOG_SCHEMA
            or catalog.get("production_recommendations") != "DISABLED"
            or catalog.get("all_world_leagues_complete") is not False
            or not clock_ok(catalog.get("as_of_utc"), now, 16)
            or not isinstance(catalog.get("cards"), list)):
        status["reason"] = "CATALOG_MISSING_OR_UNSAFE"
        return input_doc, status
    # The audited snapshot retains exact historical dataset paths; even an
    # archived season is allowed only as unverified research training history.
    audited_paths = defaultdict(list)
    if (isinstance(wide, dict)
            and wide.get("schema") == "football-king-wide-free-leagues-v1"
            and wide.get("status") == "RESEARCH_ONLY"
            and wide.get("production_recommendations") == "DISABLED"
            and wide.get("automatic_prediction_training") is False
            and wide.get("market_odds_available") is False
            and clock_ok(wide.get("collected_utc"), now, 36)
            and isinstance(wide.get("league_coverage"), list)):
        for entry in wide["league_coverage"][:160]:
            if (not isinstance(entry, dict)
                    or entry.get("provider") != "openfootball_json"
                    or entry.get("access_status") != "FETCHED"
                    or entry.get("season_scope") not in (
                        "CURRENT_SEASON_FILE", "ARCHIVED_SEASON_ONLY")):
                continue
            league = entry.get("league")
            path = entry.get("dataset_path")
            if (isinstance(league, str) and isinstance(path, str)
                    and ALLOWED_LEAGUE.fullmatch(league)
                    and ALLOWED_PATH.fullmatch(path)):
                audited_paths[league].append(path)
    candidates = []
    for card in catalog["cards"][:400]:
        if not isinstance(card, dict):
            continue
        league = card.get("id")
        if (not isinstance(league, str) or not ALLOWED_LEAGUE.fullmatch(league)
                or league in SIX):
            continue
        files = card.get("source_files")
        source_paths = [f for f in files if isinstance(f, str)
                        and ALLOWED_PATH.fullmatch(f)] if isinstance(files, list) else []
        for path in audited_paths.get(league, []):
            if path not in source_paths:
                source_paths.append(path)
        if not source_paths and league not in GERMAN:
            continue
        ident = card.get("sportsdb_directory_id")
        if not (isinstance(ident, str) and ident.isdecimal() and 3 <= len(ident) <= 9):
            ident = None
        if not ident and league not in GERMAN:
            # There is no second feed to corroborate this catalogue entry.
            continue
        candidates.append((league, source_paths, ident))
    status["eligible_catalogue_leagues"] = len(candidates)
    candidates.sort(key=lambda x: (x[0] not in GERMAN, x[0]))
    # Reserve one non-German slot to audit Japan J1. The 2026 season
    # transition requires its own history/fixture coverage monitoring.
    # All other countries continue the bounded daily rotating schedule.
    priority = [c for c in candidates
                if c[0] in GERMAN or c[0] in JAPAN_PRIORITY]
    remainder = [c for c in candidates
                 if c[0] not in GERMAN and c[0] not in JAPAN_PRIORITY]
    if remainder:
        start = now.toordinal() % len(remainder) if hasattr(now, "toordinal") else now.date().toordinal() % len(remainder)
        remainder = remainder[start:] + remainder[:start]
    selected = (priority + remainder)[:min(max(0, max_leagues), MAX_LEAGUES_PER_RUN)]
    status["requested_leagues"] = len(selected)
    status["japan_j1_selected_for_source_audit"] = any(
        c[0] == "japan_j1" for c in selected)
    status["japan_j1_is_not_automatically_forecast_qualified"] = True
    read = loader or get_json
    start_time = time.monotonic()

    def request(url):
        if (status["request_count"] >= MAX_CALLS
                or time.monotonic() - start_time > MAX_ELAPSED_SECONDS):
            raise TimeoutError("REQUEST_OR_TIME_BUDGET")
        status["request_count"] += 1
        return read(url)

    for league, paths, sportsdb_id in selected:
        diagnosis = {"league": league, "status": "HOLD",
                     "reason": "NO_QUALIFIED_TWO_SOURCE_FIXTURE",
                     "historical_games": 0, "raw_fixture_observations": 0,
                     "two_source_schedule_agreements": 0,
                     "sources_successful": []}
        history = []
        for path in paths[:2]:
            try:
                loaded = request(OPENFOOTBALL + path)
                parsed = historical(loaded, now=now, source_path=path)
                if parsed:
                    history = parsed
                    diagnosis["sources_successful"].append("openfootball_json")
                    break
            except (OSError, ValueError, UnicodeError, TimeoutError,
                    TypeError, OverflowError, KeyError):
                continue
        german_doc = None
        if league in GERMAN:
            season = now.year if now.month >= 7 else now.year-1
            try:
                german_doc = request(OPENLIGA + GERMAN[league] + "/" + str(season))
                diagnosis["sources_successful"].append("openligadb")
                if len(history) < 30:
                    history = openliga_history(german_doc, now)
            except (OSError, ValueError, UnicodeError, TimeoutError, TypeError):
                german_doc = None
        diagnosis["historical_games"] = len(history)
        if len(history) < 30:
            diagnosis["reason"] = "INSUFFICIENT_VERIFIABLE_PREVIOUS_DATE_RESULTS"
            status["leagues"].append(diagnosis)
            continue
        fixtures = []
        if sportsdb_id:
            try:
                fixtures.extend(sportsdb_events(
                    request(SPORTSDB + sportsdb_id), sportsdb_id, now))
                diagnosis["sources_successful"].append("thesportsdb")
            except (OSError, ValueError, UnicodeError, TimeoutError, TypeError):
                pass
        if german_doc is not None:
            german_schedule = openliga_events(german_doc, now)
            fixtures.extend(german_schedule)
            if sportsdb_id:
                # eventsnextleague.php returns only one event on the free
                # tier. Two small date-specific requests may independently
                # check the first upcoming German matchdays.
                dates = []
                for row in german_schedule:
                    day = timestamp(row["kickoff_utc"]).astimezone(
                        ZoneInfo("Europe/Berlin")).date().isoformat()
                    if day not in dates:
                        dates.append(day)
                    if len(dates) == 2:
                        break
                seen_sportsdb = {row["provider_event_id"] for row in fixtures
                                 if row["provider"] == "thesportsdb"}
                for day in dates:
                    try:
                        url = SPORTSDB_DAY + urlencode({
                            "d": day, "l": sportsdb_id})
                        extras = sportsdb_events(request(url), sportsdb_id, now)
                        for row in extras:
                            if row["provider_event_id"] not in seen_sportsdb:
                                fixtures.append(row)
                                seen_sportsdb.add(row["provider_event_id"])
                    except (OSError, ValueError, UnicodeError, TimeoutError, TypeError):
                        continue
        fixtures.extend(market_events(market, league, now))
        diagnosis["raw_fixture_observations"] = len(fixtures)
        matches = count_pairs(fixtures, league, history)
        diagnosis["two_source_schedule_agreements"] = matches
        status["historical_games"] += len(history)
        status["source_scheduled_fixtures"] += len(fixtures)
        status["two_source_schedule_agreements"] += matches
        if fixtures:
            input_doc["leagues"].append({
                "id": league, "history": history,
                "fixture_observations": fixtures[:MAX_FIXTURES_PER_LEAGUE]})
            diagnosis["status"] = "RESEARCH_ONLY"
            diagnosis["reason"] = ("TWO_DIFFERENT_PUBLISHERS_MATCHED_SCHEDULE"
                                   if matches else "ONLY_SINGLE_OR_UNMATCHED_FEEDS")
        else:
            diagnosis["reason"] = "NO_FRESH_FIXTURE_OBSERVATIONS"
        status["leagues"].append(diagnosis)
    if input_doc["leagues"]:
        status["status"] = "RESEARCH_ONLY"
        status["reason"] = "UNVERIFIED_RESEARCH_INPUT_NO_BETTING"
    return input_doc, status


def publish(site, *, catalogue, market, output):
    site = Path(site)
    data, status = build(safe_json(catalogue), safe_json(market),
                         wide=safe_json("sources/wide_latest.json"))
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"
    if len(encoded.encode("utf-8")) > MAX_SNAPSHOT:
        data["leagues"] = []
        status["status"] = "HOLD"
        status["reason"] = "INPUT_TOO_LARGE"
        encoded = json.dumps(data, ensure_ascii=False) + "\n"
    output.write_text(encoded, encoding="utf-8")
    (site / "worldwide_source_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key:status[key] for key in
                      ("status", "reason", "eligible_catalogue_leagues",
                       "requested_leagues", "historical_games",
                       "source_scheduled_fixtures", "two_source_schedule_agreements",
                       "request_count", "production_recommendations")},
                     ensure_ascii=False))
    return status


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="app/site")
    parser.add_argument("--catalogue", default="app/site/global_league_catalog.json")
    parser.add_argument("--market", default="market/latest.json")
    parser.add_argument("--output", default="sources/worldwide_verified_latest.json")
    args = parser.parse_args()
    publish(args.site, catalogue=args.catalogue, market=args.market, output=args.output)
