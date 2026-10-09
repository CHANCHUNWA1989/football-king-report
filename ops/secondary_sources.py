"""Read-only and quota-conscious extra football sources for Football King.

Every source is independent, optional and reports coverage limitations. This
collector NEVER changes the 1X2 bookmaker market or historical prediction.
No raw commercial odds, provider payload, credentials or paid-tier calls are
published. Credentials only appear as request headers, never as URL/query/log.
"""
import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode

LEAGUES = ("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1")
SD_BD = dict(zip(LEAGUES, (4328, 4329, 4331, 4335, 4332, 4334)))
AF_ID = dict(zip(LEAGUES, (39, 40, 78, 140, 135, 61)))
FD_CODE = dict(zip(LEAGUES, ("PL", "ELC", "BL1", "PD", "SA", "FL1")))
SPORTMONKS_FREE_IDS = (271, 501)  # Danish and Scottish leagues, not six main leagues.
MAX_RESPONSE = 1200000
MAX_FIXTURE_ROWS = 80
MAX_CALLS = {"thesportsdb": 6, "api_football": 6, "football_data_org": 6, "sportmonks": 2}


def utc(value, naive_utc=False):
    if not isinstance(value, str) or not value or "T" not in value:
        raise ValueError("INVALID_TIMESTAMP")
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        if not naive_utc:
            raise ValueError("TIMESTAMP_NO_TIMEZONE")
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).isoformat()


def fixture(league, home, away, kickoff, event_id, *, score=None, status="UNKNOWN"):
    if not (league in LEAGUES and isinstance(home, str) and home.strip()
            and isinstance(away, str) and away.strip() and home != away
            and isinstance(event_id, (str, int)) and str(event_id)):
        return None
    try:
        t = utc(kickoff, naive_utc=True)
    except (ValueError, TypeError, OverflowError):
        return None
    out = {"league": league, "home": home.strip()[:100], "away": away.strip()[:100],
           "kickoff_utc": t, "provider_event_id": str(event_id)[:80],
           "status": status if status in ("SCHEDULED", "FINISHED") else "UNKNOWN",
           "score_ft": None}
    if (out["status"] == "FINISHED" and isinstance(score, list)
            and len(score) == 2 and all(type(s) is int and 0 <= s <= 30 for s in score)):
        out["score_ft"] = score
    return out


def parse_sportsdb(league, body):
    rows = body.get("events", []) if isinstance(body, dict) else None
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise ValueError("BAD_SPORTSDB_RESPONSE")
    result = []
    for r in rows[:30]:
        if not isinstance(r, dict) or str(r.get("idLeague")) != str(SD_BD[league]):
            continue
        started = r.get("strTimestamp")
        # strTimestamp on TheSportsDB v1 is UTC but may be timezone-naive.
        score = [r.get("intHomeScore"), r.get("intAwayScore")]
        if all(s is not None and str(s).isdigit() for s in score):
            score = [int(x) for x in score]
        else:
            score = None
        is_final = str(r.get("strStatus", "")).lower() in ("match finished", "ft", "finished")
        f = fixture(league, r.get("strHomeTeam"), r.get("strAwayTeam"), started,
                    r.get("idEvent"), score=score,
                    status="FINISHED" if is_final else "SCHEDULED")
        if f:
            result.append(f)
    return result[:1]  # official free next-league endpoint maximum is one event


def parse_api_football(league, body):
    if not isinstance(body, dict):
        raise ValueError("BAD_API_FOOTBALL_RESPONSE")
    errors = body.get("errors")
    if errors and errors != [] and errors != {}:
        raise ValueError("API_FOOTBALL_PROVIDER_ERRORS")
    rows = body.get("response", [])
    if not isinstance(rows, list):
        raise ValueError("BAD_API_FOOTBALL_FIXTURES")
    result = []
    for r in rows[:MAX_FIXTURE_ROWS]:
        if not isinstance(r, dict):
            continue
        game = r.get("fixture") or {}
        lg = r.get("league") or {}
        teams = r.get("teams") or {}
        sc = r.get("score") or {}
        if lg.get("id") != AF_ID[league]:
            continue
        final = (game.get("status") or {}).get("short") == "FT"
        h = (teams.get("home") or {}).get("name")
        a = (teams.get("away") or {}).get("name")
        score = (sc.get("fulltime") or {})
        f = fixture(league, h, a, game.get("date"), game.get("id"),
                    score=[score.get("home"), score.get("away")],
                    status="FINISHED" if final else "SCHEDULED")
        if f:
            result.append(f)
    return result[:MAX_FIXTURE_ROWS]


def parse_football_data(league, body):
    if not isinstance(body, dict):
        raise ValueError("BAD_FOOTBALL_DATA_RESPONSE")
    rows = body.get("matches", [])
    if not isinstance(rows, list):
        raise ValueError("BAD_FOOTBALL_DATA_FIXTURES")
    result = []
    for r in rows[:MAX_FIXTURE_ROWS]:
        if not isinstance(r, dict):
            continue
        if (r.get("competition") or {}).get("code") not in (None, FD_CODE[league]):
            continue
        home = (r.get("homeTeam") or {}).get("name")
        away = (r.get("awayTeam") or {}).get("name")
        fulltime = ((r.get("score") or {}).get("fullTime") or {})
        final = r.get("status") == "FINISHED"
        f = fixture(league, home, away, r.get("utcDate"), r.get("id"),
                    score=[fulltime.get("home"), fulltime.get("away")],
                    status="FINISHED" if final else "SCHEDULED")
        if f:
            result.append(f)
    return result[:MAX_FIXTURE_ROWS]


def parse_sportmonks(body):
    if not isinstance(body, dict):
        raise ValueError("BAD_SPORTMONKS_RESPONSE")
    data = body.get("data", {})
    if not isinstance(data, dict):
        raise ValueError("BAD_SPORTMONKS_LEAGUE")
    return data.get("id") if data.get("id") in SPORTMONKS_FREE_IDS else None


def read_json(url, headers, *, opener=urlopen):
    if not url.startswith("https://"):
        raise ValueError("HTTPS_REQUIRED")
    # Prevent redirects to unrelated hosts leaking bearer keys.
    # urllib follows redirects by default, so credentialed providers use
    # a no-redirect handler in the collector's default requester.
    req = Request(url, headers={"Accept": "application/json",
                                "User-Agent": "FootballKingFreeSourceAudit/1.0",
                                **headers})
    with opener(req, timeout=13) as response:
        raw = response.read(MAX_RESPONSE+1)
    if len(raw) > MAX_RESPONSE:
        raise ValueError("PROVIDER_RESPONSE_TOO_LARGE")
    return json.loads(raw.decode("utf-8"))


class NoRedirect:
    def __call__(self, req, timeout):
        from urllib.request import build_opener, HTTPRedirectHandler
        class RejectRedirect(HTTPRedirectHandler):
            def redirect_request(self, request, fp, code, msg, headers, newurl):
                raise ValueError("PROVIDER_REDIRECT_REJECTED")
        return build_opener(RejectRedirect()).open(req, timeout=timeout)


def fetch(provider, url, headers, *, requester=None):
    try:
        body = read_json(url, headers, opener=requester or NoRedirect())
        if not isinstance(body, dict):
            return None, "INVALID_DATA"
        return body, "OK"
    except HTTPError as err:
        # Do not include URLs, response bodies or secrets in logs.
        if err.code in (401, 403):
            return None, "KEY_OR_PLAN_REJECTED"
        if err.code == 429:
            return None, "RATE_LIMITED"
        return None, "HTTP_ERROR"
    except (URLError, TimeoutError, OSError):
        return None, "NETWORK_ERROR"
    except (ValueError, UnicodeError, json.JSONDecodeError):
        return None, "INVALID_DATA"


def base(name, configured, note):
    return {"provider": name, "status": "NOT_CONFIGURED" if not configured else "HOLD",
            "configured": configured, "source_scope": note,
            "calls_attempted": 0, "counts_by_league": {l: 0 for l in LEAGUES},
            "sampled_fixture_count": 0, "warnings": [],
            "league_result_verification_complete": False, "can_replace_1x2_market": False,
            "original_bookmaker_odds_redistributed": False,
            "production_recommendations": "DISABLED"}


def collect(*, now=None, keys=None, requester=None):
    now = now or datetime.now(timezone.utc)
    keys = keys if keys is not None else os.environ
    end = (now + timedelta(days=8)).date().isoformat()
    start = (now - timedelta(days=2)).date().isoformat()
    season = now.year if now.month >= 7 else now.year-1
    configs = [
        ("thesportsdb", True, "FREE_V1_NEXT_ONE_EVENT_PER_LEAGUE"),
        ("api_football", bool(keys.get("API_FOOTBALL_KEY")), "FREE_SEASON_RESTRICTIONS_100_PER_DAY"),
        ("football_data_org", bool(keys.get("FOOTBALL_DATA_ORG_TOKEN")), "FREE_DELAYED_SCORES_10_PER_MIN"),
        ("sportmonks", bool(keys.get("SPORTMONKS_API_TOKEN")), "FREE_ONLY_DANISH_AND_SCOTTISH_LEAGUES"),
    ]
    report = {"schema": "football-king-extra-source-audit-v1",
              "started_utc": now.isoformat(), "collected_utc": None,
              "source_tier": "FREE_ONLY", "status": "RESEARCH_ONLY",
              "providers": [], "sampled_fixtures": [],
              "coverage_is_complete": False, "six_league_independent_results_verified": False,
              "odds_fallback_confirmed": False,
              "original_api_payload_redistributed": False,
              "production_recommendations": "DISABLED"}
    for name, enabled, note in configs:
        state = base(name, enabled, note)
        if not enabled:
            state["warnings"].append("GITHUB_REPOSITORY_SECRET_REQUIRED")
            report["providers"].append(state)
            continue
        requests = []
        if name == "thesportsdb":
            for league, ident in SD_BD.items():
                requests.append((league, "https://www.thesportsdb.com/api/v1/json/123/"
                                 f"eventsnextleague.php?id={ident}", {}))
        elif name == "api_football":
            for league, ident in AF_ID.items():
                # Six GETs a day, no paid odds endpoints, no deep pagination.
                requests.append((league,
                    "https://v3.football.api-sports.io/fixtures?" +
                    urlencode({"league": ident, "season": season, "next": 3}),
                    {"x-apisports-key": keys["API_FOOTBALL_KEY"]}))
        elif name == "football_data_org":
            for league, ident in FD_CODE.items():
                requests.append((league,
                    f"https://api.football-data.org/v4/competitions/{ident}/matches?"+
                    urlencode({"dateFrom": start, "dateTo": end}),
                    {"X-Auth-Token": keys["FOOTBALL_DATA_ORG_TOKEN"]}))
        elif name == "sportmonks":
            for ident in SPORTMONKS_FREE_IDS:
                # Header-auth only. Never expose api_token in query URLs or artifacts.
                requests.append((None, f"https://api.sportmonks.com/v3/football/leagues/{ident}",
                                 {"Authorization": keys["SPORTMONKS_API_TOKEN"]}))
        if len(requests) > MAX_CALLS[name]:
            raise ValueError("REQUEST_BUDGET_EXCEEDED")
        failures = set()
        sportmonks_ok = 0
        for league, url, headers in requests:
            state["calls_attempted"] += 1
            body, outcome = fetch(name, url, headers, requester=requester)
            if outcome != "OK":
                failures.add(outcome)
                if outcome in ("RATE_LIMITED", "KEY_OR_PLAN_REJECTED"):
                    break  # Never repeatedly hammer quota/invalid keys.
                continue
            try:
                if name == "thesportsdb":
                    rows = parse_sportsdb(league, body)
                elif name == "api_football":
                    rows = parse_api_football(league, body)
                elif name == "football_data_org":
                    rows = parse_football_data(league, body)
                else:
                    sportmonks_ok += int(parse_sportmonks(body) is not None)
                    rows = []
            except (ValueError, KeyError, TypeError):
                failures.add("UNEXPECTED_SCHEMA")
                rows = []
            for row in rows:
                row["provider"] = name
                report["sampled_fixtures"].append(row)
                state["counts_by_league"][league] += 1
        state["sampled_fixture_count"] = sum(state["counts_by_league"].values())
        if name == "sportmonks":
            state["additional_non_target_free_leagues"] = sportmonks_ok
        state["warnings"] = sorted(failures)
        if failures:
            state["status"] = "PARTIAL" if state["sampled_fixture_count"] or sportmonks_ok else "HOLD"
        elif state["sampled_fixture_count"] or sportmonks_ok:
            state["status"] = "PARTIAL_COVERAGE"
        else:
            state["status"] = "NO_FIXTURES_RETURNED"
        if name == "sportmonks":
            state["warnings"].append("FREE_PLAN_DOES_NOT_COVER_THE_SIX_TARGET_LEAGUES")
        if name == "thesportsdb":
            state["warnings"].append("FREE_NEXT_LEAGUE_RETURNS_AT_MOST_ONE_EVENT")
        report["providers"].append(state)
    report["sampled_fixtures"] = report["sampled_fixtures"][:150]
    report["collected_utc"] = datetime.now(timezone.utc).isoformat() if now.tzinfo else now.isoformat()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="sources/latest.json")
    args = parser.parse_args()
    result = collect()
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    # Print only non-secret statuses.
    print(json.dumps({"status": result["status"],
        "providers": [{k: s[k] for k in ("provider","status","sampled_fixture_count","calls_attempted","warnings")}
                      for s in result["providers"]],
        "production_recommendations":"DISABLED"}, ensure_ascii=False))
