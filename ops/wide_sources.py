"""Free extra-league coverage without paid keys, odds or guessed kickoff times.

OpenFootball football.json (CC0/public domain) provides exact source-file
availability and sometimes historical scores; *season directory*, not match
date, decides CURRENT_VS_ARCHIVE. Unzoned "time" is never cast as UTC.
OpenLigaDB has an openly readable user-contributed German match API.
Neither can replace bookmaker 1X2 data or enter prediction training without
an independent, point-in-time source validation process.
"""
import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler

NOW_LEAGUES = (
    ("epl", "英超", "2026-27/en.1.json"),
    ("championship", "英冠", "2026-27/en.2.json"),
    ("bundesliga", "德甲", "2026-27/de.1.json"),
    ("laliga", "西甲", "2026-27/es.1.json"),
    ("seriea", "意甲", "2026-27/it.1.json"),
    ("ligue1", "法甲", "2026-27/fr.1.json"),
    ("eredivisie", "荷甲", "2026-27/nl.1.json"),
    ("primeira_liga", "葡超", "2026-27/pt.1.json"),
    ("brazil_serie_a", "巴甲", "2026/br.1.json"),
)
HISTORY_LEAGUES = (
    ("bundesliga2", "德乙", "2025-26/de.2.json"),
    ("league_one", "英甲", "2025-26/en.3.json"),
    ("league_two", "英乙", "2025-26/en.4.json"),
    ("segunda", "西乙", "2025-26/es.2.json"),
    ("serie_b", "意乙", "2025-26/it.2.json"),
    ("ligue2", "法乙", "2025-26/fr.2.json"),
    ("austrian_bundesliga", "奧甲", "2025-26/at.1.json"),
    ("austria_liga2", "奧乙", "2025-26/at.2.json"),
    ("belgian_pro", "比甲", "2025-26/be.1.json"),
    ("greek_superleague", "希超", "2025-26/gr.1.json"),
    ("scottish_premiership", "蘇超", "2025-26/sco.1.json"),
    ("turkish_superlig", "土超", "2025-26/tr.1.json"),
    ("argentina_primera", "阿根廷甲", "2025/ar.1.json"),
    ("brazil_serie_b", "巴乙", "2025/br.2.json"),
    ("china_superleague", "中超", "2025/cn.1.json"),
    ("colombia_primera", "哥倫比亞甲", "2025/co.1.json"),
    ("japan_j1", "日職J1", "2025/jp.1.json"),
    ("usa_mls", "美職聯", "2025/mls.json"),
)
# 2026 German source existence must be confirmed by the API, not assumed.
GERMAN_LEAGUES = (
    ("bundesliga", "德甲", "bl1"),
    ("bundesliga2", "德乙", "bl2"),
    ("germany_liga3", "德丙", "bl3"),
)
SCHEMA = "football-king-wide-free-leagues-v1"
UPSTREAM = "https://raw.githubusercontent.com/openfootball/football.json/master/"
MAX_RESPONSE = 1200000
MAX_FILES = len(NOW_LEAGUES) + len(HISTORY_LEAGUES)
MAX_REQUESTS = MAX_FILES + len(GERMAN_LEAGUES)
MAX_EXAMPLES = 18
MAX_ELAPSED = 125
PROVIDER_NAMES = ("openfootball_json", "openligadb")
LEAGUE_IDS = {x[0] for x in NOW_LEAGUES + HISTORY_LEAGUES + GERMAN_LEAGUES}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("UNTRUSTED_REDIRECT")


def request_json(url, *, opener=None):
    if not (url.startswith(UPSTREAM) or url.startswith("https://api.openligadb.de/getmatchdata/")):
        raise ValueError("DISALLOWED_PROVIDER_URL")
    client = opener or build_opener(NoRedirect()).open
    req = Request(url, headers={"Accept": "application/json",
                               "User-Agent": "FootballKingFreeCoverage/1.0"})
    with client(req, timeout=12) as response:
        raw = response.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise ValueError("PUBLIC_RESPONSE_TOO_LARGE")
    return json.loads(raw.decode("utf-8"))


def utc_clock(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_CLOCK")
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return date.astimezone(timezone.utc)


def scored(row):
    if not isinstance(row, list) or len(row) != 2:
        return False
    return all(type(x) is int and 0 <= x <= 30 for x in row)


def read_openfootball(league, name, path, doc, *, current):
    if not isinstance(doc, dict) or not isinstance(doc.get("matches"), list):
        raise ValueError("INVALID_OPENFOOTBALL_SCHEMA")
    records = doc["matches"]
    if len(records) > 1600:
        raise ValueError("TOO_MANY_MATCHES")
    n_scores = n_dates = n_unzoned = 0
    sample = []
    for row in records:
        if not isinstance(row, dict):
            continue
        if not all(isinstance(row.get(key), str) and row[key].strip()
                   for key in ("team1", "team2")):
            continue
        day = row.get("date")
        if isinstance(day, str):
            try:
                datetime.strptime(day, "%Y-%m-%d")
                n_dates += 1
            except ValueError:
                day = None
        else:
            day = None
        t = row.get("time")
        if isinstance(t, str) and t:
            n_unzoned += 1
        rawscore = row.get("score")
        score = rawscore.get("ft") if isinstance(rawscore, dict) else None
        if scored(score):
            n_scores += 1
        if len(sample) < 2 and day:
            sample.append({"league": league, "source": "openfootball_json",
                           "home": row["team1"][:100], "away": row["team2"][:100],
                           "calendar_date_only": day,
                           "time_is_unzoned_not_safely_usable_as_utc": bool(t),
                           "score_full_time": list(score) if scored(score) else None,
                           "kickoff_utc": None, "source_path": path,
                           "production_recommendations": "DISABLED"})
    return {
        "league": league, "name_zh": name, "provider": "openfootball_json",
        "dataset_path": path, "access_status": "FETCHED",
        "season_scope": "CURRENT_SEASON_FILE" if current else "ARCHIVED_SEASON_ONLY",
        "records": len(records), "dated_fixtures": n_dates,
        "reported_ft_scores_unverified": n_scores,
        "unzoned_time_rows": n_unzoned,
        "precise_utc_kickoffs_confirmed": 0,
        "source_collection_is_asof_verified": False,
        "usable_for_live_betting": False,
        "sample": sample,
    }


def parse_openliga(league, name, rows, now):
    if not isinstance(rows, list) or len(rows) > 1300:
        raise ValueError("BAD_OPENLIGA_MATCHES")
    finished = 0
    precise = 0
    examples = []
    upcoming = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            ko = utc_clock(row["matchDateTimeUTC"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        precise += 1
        home = (row.get("team1") or {}).get("teamName")
        away = (row.get("team2") or {}).get("teamName")
        if not all(isinstance(x, str) and x for x in (home, away)):
            continue
        if row.get("matchIsFinished") is True:
            finished += 1
        if now <= ko <= now + timedelta(days=14):
            upcoming += 1
            if len(examples) < 3:
                examples.append({
                    "league": league, "source": "openligadb",
                    "home": home[:100], "away": away[:100],
                    "kickoff_utc": ko.isoformat(),
                    "provider_event_id": str(row.get("matchID", ""))[:60],
                    "status": "FINISHED" if row.get("matchIsFinished") else "SCHEDULED",
                    "score_full_time": None,  # results are not independently attested
                    "production_recommendations": "DISABLED",
                })
    return {
        "league": league, "name_zh": name, "provider": "openligadb",
        "access_status": "FETCHED",
        "season_scope": "2026_SEASON_REQUEST_NOT_FRESHNESS_PROOF",
        "records": len(rows), "dated_fixtures": precise,
        "reported_ft_scores_unverified": finished,
        "precise_utc_kickoffs_confirmed": precise,
        "upcoming_14_days": upcoming,
        "source_collection_is_asof_verified": False,
        "usable_for_live_betting": False,
        "sample": examples,
    }


def failure_scope(league, name, provider, season, failure):
    return {
        "league": league, "name_zh": name, "provider": provider,
        "access_status": failure,
        "season_scope": season, "records": 0, "dated_fixtures": 0,
        "reported_ft_scores_unverified": 0, "precise_utc_kickoffs_confirmed": 0,
        "usable_for_live_betting": False, "sample": []
    }


def failure(err):
    if isinstance(err, HTTPError):
        return "NO_FILE_OR_ACCESS" if err.code in (403, 404) else (
            "RATE_LIMITED" if err.code == 429 else "HTTP_ERROR")
    if isinstance(err, (TimeoutError, URLError, OSError)):
        return "NETWORK_ERROR"
    return "INVALID_SCHEMA_OR_RESPONSE"


def collect(now=None, *, loader=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    season = now.year if now.month >= 7 else now.year-1
    # The first 9 catalog references were verified in 2026; URLs change
    # automatically each new season. A not-yet-published season gives a safe
    # NO_FILE_OR_ACCESS instead of reusing a stale former season as CURRENT.
    current_range = f"{season}-{(season+1)%100:02d}"
    def resolve_path(key):
        if key.startswith("2026-27/"):
            return key.replace("2026-27/", current_range + "/", 1)
        if key == "2026/br.1.json":
            return f"{now.year}/br.1.json"
        return key
    jobs = (
        [(league, name, file, "openfootball_json", True)
         for league, name, file in NOW_LEAGUES]
        + [(league, name, file, "openfootball_json", False)
           for league, name, file in HISTORY_LEAGUES]
        + [(league, name, shortcut, "openligadb", True)
           for league, name, shortcut in GERMAN_LEAGUES]
    )
    if len(jobs) != MAX_REQUESTS:
        raise ValueError("REQUEST_BUDGET_NOT_FIXED")
    gathered = []
    begin = time.monotonic()
    calls = 0
    for league, name, key, provider, current in jobs:
        if time.monotonic() - begin > MAX_ELAPSED:
            gathered.append(failure_scope(league, name, provider,
                                          "CURRENT_SEASON" if current else "ARCHIVE",
                                          "TIME_BUDGET_EXHAUSTED"))
            continue
        # Historical filenames are discovered from actual openfootball GitHub
        # directories. Never rewrite an archive file to masquerade as current.
        actual_path = resolve_path(key) if provider == "openfootball_json" and current else key
        url = (UPSTREAM + actual_path) if provider == "openfootball_json" else (
            f"https://api.openligadb.de/getmatchdata/{key}/{season}")
        calls += 1
        try:
            doc = (loader or request_json)(url)
            if provider == "openfootball_json":
                state = read_openfootball(league, name, actual_path, doc, current=current)
            else:
                state = parse_openliga(league, name, doc, now)
        except (HTTPError, URLError, OSError, TimeoutError, ValueError, TypeError,
                OverflowError, KeyError, UnicodeError, json.JSONDecodeError) as ex:
            state = failure_scope(league, name, provider,
                                  "CURRENT_SEASON" if current else "ARCHIVE", failure(ex))
        gathered.append(state)
    providers = []
    for provider in PROVIDER_NAMES:
        subsets = [x for x in gathered if x["provider"] == provider]
        count = sum(x["access_status"] == "FETCHED" for x in subsets)
        providers.append({
            "provider": provider, "configured": True, "requires_key": False,
            "requested_league_files": len(subsets),
            "accessible_league_files": count,
            "failed_league_files": len(subsets)-count,
            "status": "PARTIAL_COVERAGE" if count else "HOLD",
            "odds_market_fallback_available": False,
            "production_recommendations": "DISABLED",
        })
    all_samples = []
    for item in gathered:
        all_samples.extend(item.get("sample", []))
    output = {
        "schema": SCHEMA,
        "collected_utc": datetime.now(timezone.utc).isoformat(),
        "status": "RESEARCH_ONLY",
        "providers": providers, "league_coverage": gathered,
        "provider_calls_attempted": calls, "provider_call_budget": MAX_REQUESTS,
        "configured_season": season,
        "league_file_total": len(gathered),
        "successful_league_files": sum(i["access_status"] == "FETCHED" for i in gathered),
        "current_season_file_successes": sum(
            i["access_status"] == "FETCHED" and
            i["season_scope"] == "CURRENT_SEASON_FILE" for i in gathered),
        "historical_only_file_successes": sum(
            i["access_status"] == "FETCHED" and
            i["season_scope"] == "ARCHIVED_SEASON_ONLY" for i in gathered),
        "source_samples": all_samples[:MAX_EXAMPLES],
        "timezone_of_openfootball_match_time_unconfirmed": True,
        "historic_openfootball_season_is_not_live": True,
        "results_independently_verified": False,
        "automatic_prediction_training": False,
        "market_odds_available": False,
        "production_recommendations": "DISABLED",
        "warning": "Season filenames are real but upstream dates/scores can be stale; unzoned times never become precise UTC.",
    }
    return output


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--output", default="wide-result.json")
    args = cli.parse_args()
    result = collect()
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps({
        "providers": result["providers"],
        "league_files": result["league_file_total"],
        "fetched": result["successful_league_files"],
        "current_fetched": result["current_season_file_successes"],
        "archived_fetched": result["historical_only_file_successes"],
        "request_count": result["provider_calls_attempted"],
        "production_recommendations": "DISABLED",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
