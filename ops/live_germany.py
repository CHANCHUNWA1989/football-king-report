"""Hourly community German football fixture/score observations (research-only).

OpenLigaDB bl1/bl2/bl3 GET /getmatchdata/<league> is free and keyless,
community-maintained and subject to ODbL. Results are NOT an official live
score guarantee and can NEVER rewrite a model prediction or produce betting
advice. Source timestamps are snapshot collection time, not event update time.
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler

SHORTCUTS = {"bundesliga": "bl1", "bundesliga2": "bl2", "germany_liga3": "bl3"}
API_BASE = "https://api.openligadb.de/getmatchdata/"
API_LICENSE = "https://www.openligadb.de/lizenz"
MAX_BYTES = 1000000
MAX_MATCHES_PER_GROUP = 30
MAX_OUTPUT_MATCHES = 70
WINDOW_PAST_DAYS = 3
WINDOW_NEXT_DAYS = 10


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("UNTRUSTED_REDIRECT")


def iso(value):
    if not isinstance(value, str) or not value:
        raise ValueError("MISSING_KICKOFF")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    # 'matchDateTimeUTC' is explicitly UTC in the documented API schema.
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def read_json(url, *, opener=None):
    if url not in (API_BASE + x for x in SHORTCUTS.values()):
        raise ValueError("DISALLOWED_FREE_API_URL")
    req = Request(url, headers={"Accept": "application/json",
                                "User-Agent": "FootballKingFreeGermanFixtures/1.0"})
    client = opener or build_opener(NoRedirect()).open
    with client(req, timeout=13) as r:
        payload = r.read(MAX_BYTES+1)
    if len(payload) > MAX_BYTES:
        raise ValueError("GERMAN_RESPONSE_TOO_LARGE")
    return json.loads(payload.decode("utf-8"))


def parse(league, payload, now):
    if league not in SHORTCUTS or not isinstance(payload, list) or len(payload) > MAX_MATCHES_PER_GROUP:
        raise ValueError("BAD_GERMAN_MATCHDAY")
    games = []
    for r in payload:
        if not isinstance(r, dict):
            continue
        try:
            if r.get("leagueShortcut") not in (None, SHORTCUTS[league]):
                continue
            ko = iso(r["matchDateTimeUTC"])
            if not (now - timedelta(days=WINDOW_PAST_DAYS) <= ko <= now + timedelta(days=WINDOW_NEXT_DAYS)):
                continue
            home, away = ((r.get("team1") or {}).get("teamName"),
                          (r.get("team2") or {}).get("teamName"))
            event_id = r.get("matchID")
            if (not all(isinstance(s, str) and s.strip() for s in (home, away))
                    or home == away or type(event_id) is not int or event_id <= 0):
                continue
            done = r.get("matchIsFinished") is True
            score = None
            if done:
                full = [x for x in (r.get("matchResults") or [])
                        if isinstance(x, dict) and x.get("resultTypeID") == 2]
                if len(full) == 1:
                    raw = [full[0].get("pointsTeam1"), full[0].get("pointsTeam2")]
                    if all(type(v) is int and 0 <= v <= 30 for v in raw):
                        score = raw
            state = ("FINISHED_CONFIRMED_BY_SOURCE" if done and score is not None else
                     "FINISHED_SCORE_PENDING" if done else
                     "STARTED_STATUS_UNCONFIRMED" if ko <= now else "SCHEDULED")
            games.append({
                "league": league, "home": home.strip()[:120], "away": away.strip()[:120],
                "provider_match_id": event_id, "kickoff_utc": ko.isoformat(),
                "status": state, "score_ft": score,
            })
        except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
            continue
    return sorted(games, key=lambda x: (x["kickoff_utc"], x["provider_match_id"]))


def collect(now=None, getter=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    result = {
        "schema": "football-king-openligadb-hourly-v1",
        "collected_utc": None, "status": "HOLD",
        "source": "OpenLigaDB", "source_type": "COMMUNITY_CONTRIBUTED_NOT_OFFICIAL_LIVE",
        "licence": "ODbL", "licence_url": API_LICENSE,
        "matchday_not_full_season": True,
        "live_second_by_second_guaranteed": False,
        "provider_last_modified_known": False,
        "calls_attempted": 0, "max_calls": 3,
        "league_coverage": [], "matches": [],
        "six_league_results_independently_verified": False,
        "replaces_bookmaker_market": False, "used_to_refit_model": False,
        "production_recommendations": "DISABLED",
    }
    for league, shortcut in SHORTCUTS.items():
        result["calls_attempted"] += 1
        try:
            rows = (getter or read_json)(API_BASE + shortcut)
            items = parse(league, rows, now)
            coverage = "AVAILABLE" if rows else "EMPTY_CURRENT_MATCHDAY"
        except HTTPError as exc:
            items = []
            coverage = "RATE_LIMITED" if exc.code == 429 else "HTTP_ERROR"
        except (URLError, TimeoutError, OSError):
            items, coverage = [], "NETWORK_ERROR"
        except (TypeError, ValueError, OverflowError, UnicodeError, AttributeError, KeyError):
            items, coverage = [], "BAD_SCHEMA"
        result["league_coverage"].append({
            "league": league, "source": "openligadb", "status": coverage,
            "matches_in_display_window": len(items),
            "production_recommendations": "DISABLED",
        })
        result["matches"].extend(items)
    result["matches"] = sorted(result["matches"], key=lambda x: (x["kickoff_utc"], x["league"]))[:MAX_OUTPUT_MATCHES]
    succeeded = sum(p["status"] in ("AVAILABLE", "EMPTY_CURRENT_MATCHDAY")
                    for p in result["league_coverage"])
    result["status"] = "RESEARCH_ONLY" if succeeded else "HOLD"
    result["collected_utc"] = datetime.now(timezone.utc).isoformat()
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="sources/live_germany_latest.json")
    args = p.parse_args()
    snapshot = collect()
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"status": snapshot["status"], "calls_attempted": snapshot["calls_attempted"],
                      "coverage": snapshot["league_coverage"], "observations": len(snapshot["matches"]),
                      "production_recommendations": "DISABLED"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
