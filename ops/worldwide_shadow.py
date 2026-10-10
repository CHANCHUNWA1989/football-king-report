"""League-agnostic, fail-closed worldwide football Shadow Mode.

A league is NOT automatically a prediction just because it appears in the
worldwide file directory. New competitions require sufficiently long historical
results AND two different, time-consistent captured fixture observations.
This sidecar does not alter the six-league verified market comparison or bets.
"""
import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from shadow_forecast import predict_league
from team_identity import team_id

SCHEMA = "football-king-worldwide-candidate-input-v1"
OUTPUT_SCHEMA = "football-king-worldwide-uncalibrated-shadow-v1"
MAX_FILE_BYTES = 2_000_000
MAX_LEAGUES = 160
MAX_HISTORY = 1300
MAX_SCHEDULES = 500
VALID_PROVIDERS = frozenset((
    "thesportsdb", "openligadb", "api_football", "football_data_org",
    "the_odds_api_fixture", "other_independent_public_fixture",
))
VALID_RESULTS = frozenset(("openfootball_json", "openligadb_results"))
LEAGUE_RE = re.compile(r"^[a-z][a-z0-9_]{1,47}$")
HK = ZoneInfo("Asia/Hong_Kong")
ALLOWED_SCHEDULE_KEYS = frozenset((
    "provider", "provider_event_id", "home", "away", "kickoff_utc",
    "captured_utc", "status", "score_ft",
))
ALLOWED_HISTORY_KEYS = frozenset((
    "home", "away", "date", "status", "score_ft", "result_source",
))


def utc(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_GLOBAL_TIMESTAMP")
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("NAIVE_GLOBAL_TIMESTAMP")
    return d.astimezone(timezone.utc)


def age_ok(value, now, hours=16):
    try:
        age = now - utc(value)
        return timedelta(minutes=-5) <= age <= timedelta(hours=hours)
    except (ValueError, TypeError, OverflowError):
        return False


def generate(doc, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    report = {
        "schema": OUTPUT_SCHEMA, "as_of_utc": now.isoformat(),
        "status": "HOLD", "reason": "NO_FRESH_TWO_SOURCE_LEAGUE_INPUT",
        "predictions": [], "predictions_count": 0, "league_results": [],
        "worldwide_predictions_are_unverified": True,
        "independent_result_attestation": False, "market_odds_available": False,
        "model_calibrated": False, "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
    }
    if (not isinstance(doc, dict) or doc.get("schema") != SCHEMA
            or doc.get("production_recommendations") != "DISABLED"
            or not age_ok(doc.get("collected_utc"), now)
            or not isinstance(doc.get("leagues"), list)
            or len(doc["leagues"]) > MAX_LEAGUES):
        return report
    seen_ids = set()
    for info in doc["leagues"]:
        if not isinstance(info, dict):
            continue
        league = info.get("id")
        if not isinstance(league, str) or not LEAGUE_RE.fullmatch(league):
            continue
        if league in seen_ids:
            # Duplicate league blocks must not permit selective cherry-picking.
            report["league_results"].append({
                "league": league, "status": "HOLD", "reason": "DUPLICATE_LEAGUE"})
            report["predictions"] = [x for x in report["predictions"] if x["league"] != league]
            continue
        seen_ids.add(league)
        history = info.get("history")
        scheduled = info.get("fixture_observations")
        if (not isinstance(history, list) or len(history) > MAX_HISTORY
                or not isinstance(scheduled, list) or len(scheduled) > MAX_SCHEDULES):
            report["league_results"].append({
                "league": league, "status": "HOLD", "reason": "INVALID_OR_EXCESSIVE_INPUT"})
            continue
        clean_history = []
        appearances = Counter()
        prior_names = defaultdict(Counter)
        today = now.astimezone(HK).date()
        for row in history:
            if (not isinstance(row, dict) or not set(row).issubset(ALLOWED_HISTORY_KEYS)
                    or row.get("status") != "FINISHED"
                    or not isinstance(row.get("result_source"), str)
                    or row["result_source"] not in VALID_RESULTS
                    or not isinstance(row.get("score_ft"), list)
                    or len(row["score_ft"]) != 2
                    or not all(type(x) is int and 0 <= x <= 20 for x in row["score_ft"])):
                continue
            home, away = row.get("home"), row.get("away")
            if not all(isinstance(x, str) and 0 < len(x) <= 100 for x in (home, away)):
                continue
            h, a = team_id(league, home), team_id(league, away)
            if not h or not a or h == a:
                continue
            try:
                day = date.fromisoformat(row["date"])
                if day >= today:
                    continue
            except (ValueError, TypeError, KeyError):
                continue
            appearances[h] += 1
            appearances[a] += 1
            prior_names[h][home] += 1
            prior_names[a][away] += 1
            clean_history.append({k: row[k] for k in (
                "date", "home", "away", "status", "score_ft")})
        candidate = defaultdict(lambda: defaultdict(list))
        for row in scheduled:
            if (not isinstance(row, dict) or not set(row).issubset(ALLOWED_SCHEDULE_KEYS)
                    or not isinstance(row.get("provider"), str)
                    or row["provider"] not in VALID_PROVIDERS
                    or not isinstance(row.get("provider_event_id"), str)
                    or not row["provider_event_id"]
                    or row.get("score_ft") is not None
                    or row.get("status") != "SCHEDULED"
                    or not age_ok(row.get("captured_utc"), now)):
                continue
            home, away = row.get("home"), row.get("away")
            if not all(isinstance(x, str) and 0 < len(x) <= 100 for x in (home, away)):
                continue
            h, a = team_id(league, home), team_id(league, away)
            if (not h or not a or h == a
                    or appearances[h] < 3 or appearances[a] < 3):
                continue
            try:
                ko = utc(row["kickoff_utc"])
                if not now + timedelta(hours=1) <= ko <= now + timedelta(days=7):
                    continue
            except (ValueError, TypeError, KeyError, OverflowError):
                continue
            candidate[(h, a)][row["provider"]].append((ko, row["provider_event_id"]))
        future = []
        for (h, a), sources in candidate.items():
            # Exactly two independent provider names, each describing the same
            # kickoff to the MINUTE. Never synthesize or average UTC times.
            if len(sources) < 2 or any(len(v) != 1 for v in sources.values()):
                continue
            values = [one[0] for one in sources.values()]
            first = values[0][0]
            if any(abs((stamp - first).total_seconds()) > 60 for stamp, _ in values):
                continue
            home = prior_names[h].most_common(1)[0][0]
            away = prior_names[a].most_common(1)[0][0]
            if home == away:
                continue
            future.append({
                "event_id": "global-" + league + "-" + h + "-" + a +
                            "-" + str(int(first.timestamp())),
                "home": home, "away": away,
                "date": first.astimezone(HK).date().isoformat(),
                "kickoff_utc": first.isoformat(),
                "score_ft": None, "status": "SCHEDULED",
            })
        prediction = predict_league(clean_history + future, league, now)
        for row in prediction:
            row["worldwide_two_distinct_schedule_feeds"] = True
            row["fixture_timestamp_independently_attested"] = False
            row["historical_results_independently_verified"] = False
            row["market_odds_available"] = False
        report["predictions"].extend(prediction)
        report["league_results"].append({
            "league": league,
            "status": "SHADOW_ONLY" if prediction else "HOLD",
            "reason": "UNCALIBRATED_RESEARCH_ONLY" if prediction
                      else "INSUFFICIENT_OR_UNCORROBORATED_EVIDENCE",
            "historical_games_before_today": len(clean_history),
            "two_source_upcoming_fixtures": len(future),
            "shadow_predictions": len(prediction),
        })
    report["predictions"].sort(key=lambda x: (
        x["kickoff_utc"], x["league"], x["event_id"]))
    report["predictions_count"] = len(report["predictions"])
    if report["predictions"]:
        report["status"] = "SHADOW_ONLY"
        report["reason"] = "ADDITIONAL_LEAGUE_UNCALIBRATED_RESEARCH_ONLY"
    return report


def publish(site, input_path="sources/worldwide_verified_latest.json"):
    site = Path(site)
    doc = None
    source = Path(input_path)
    if source.is_file() and source.stat().st_size <= MAX_FILE_BYTES:
        try:
            doc = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            doc = None
    output = generate(doc)
    (site / "worldwide_shadow.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": output["status"], "reason": output["reason"],
        "worldwide_shadow_predictions": output["predictions_count"],
        "league_reports": len(output["league_results"]),
        "production_recommendations": "DISABLED"}, ensure_ascii=False))
    return output


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--site", default="app/site")
    p.add_argument("--input", default="sources/worldwide_verified_latest.json")
    args = p.parse_args()
    publish(args.site, args.input)
