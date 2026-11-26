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
    # Native event IDs belong to a publisher namespace, not a league.
    # Inspect all bounded league blocks before eligibility filtering so that
    # even an otherwise unqualified competing binding cannot hide a conflict.
    bindings = defaultdict(set)
    for info in doc["leagues"]:
        if not isinstance(info,dict):
            continue
        league=info.get("id")
        rows=info.get("fixture_observations")
        if (not isinstance(league,str) or not LEAGUE_RE.fullmatch(league)
                or not isinstance(rows,list) or len(rows)>MAX_SCHEDULES):
            continue
        for row in rows:
            if (not isinstance(row,dict) or not set(row).issubset(ALLOWED_SCHEDULE_KEYS)
                    or not isinstance(row.get("provider"),str)
                    or row["provider"] not in VALID_PROVIDERS
                    or not isinstance(row.get("provider_event_id"),str)
                    or not 0<len(row["provider_event_id"])<=160
                    or not row["provider_event_id"].strip()
                    or not age_ok(row.get("captured_utc"),now)):
                continue
            home,away=row.get("home"),row.get("away")
            if not all(isinstance(x,str) and 0<len(x)<=100 for x in (home,away)):
                continue
            h,a=team_id(league,home),team_id(league,away)
            try:
                ko=utc(row["kickoff_utc"])
            except (KeyError,ValueError,TypeError,OverflowError):
                continue
            if h and a and h!=a:
                bindings[(row["provider"],row["provider_event_id"])].add((league,h,a,ko))
    conflicted={key for key,values in bindings.items() if len(values)>1}
    report["conflicting_provider_native_ids"]=len(conflicted)
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
        history_bindings = {}
        history_conflict = False
        exact_history_duplicates = 0
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
            # Core training deduplicates raw names. This preflight also detects
            # aliases of the same normalized home/away/date, without merging
            # uncertain team identities or rewriting original observations.
            key=(day,h,a)
            facts=(home,away,tuple(row["score_ft"]))
            if key in history_bindings:
                if history_bindings[key]!=facts:
                    history_conflict=True
                else:
                    exact_history_duplicates+=1
                continue
            history_bindings[key]=facts
            appearances[h] += 1
            appearances[a] += 1
            prior_names[h][home] += 1
            prior_names[a][away] += 1
            clean_history.append({k: row[k] for k in (
                "date", "home", "away", "status", "score_ft")})
        if history_conflict:
            report["league_results"].append({
                "league":league,"status":"HOLD",
                "reason":"CONFLICTING_NORMALIZED_HISTORY_IDENTITY",
                "historical_games_before_today":len(clean_history),
                "duplicate_history_observations":exact_history_duplicates,
                "two_source_upcoming_fixtures":0,"shadow_predictions":0})
            continue
        candidate = defaultdict(lambda: defaultdict(list))
        blocked_native_rows = 0
        blocked_pairs = set()
        for row in scheduled:
            if (not isinstance(row, dict) or not set(row).issubset(ALLOWED_SCHEDULE_KEYS)
                    or not isinstance(row.get("provider"), str)
                    or row["provider"] not in VALID_PROVIDERS
                    or not isinstance(row.get("provider_event_id"), str)
                    or not 0<len(row["provider_event_id"])<=160
                    or not row["provider_event_id"].strip()
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
            if (row["provider"],row["provider_event_id"]) in conflicted:
                blocked_native_rows+=1
                blocked_pairs.add((h,a))
                continue
            candidate[(h, a)][row["provider"]].append((ko, row["provider_event_id"]))
        future = []
        clock_conflict_pairs = 0
        for (h, a), sources in candidate.items():
            # At least two named feeds; this is metadata agreement, not
            # authentication. Reject full pair if any qualified binding conflicts.
            if ((h,a) in blocked_pairs or len(sources)<2
                    or any(len(v)!=1 for v in sources.values())):
                continue
            stamps=sorted(one[0][0] for one in sources.values())
            first=stamps[0]
            if ((stamps[-1]-first).total_seconds()>60
                    or len({t.astimezone(HK).date() for t in stamps})!=1):
                clock_conflict_pairs+=1
                continue
            # Earliest actual reported timestamp; stable under feed ordering.
            home = min(prior_names[h],key=lambda name:(-prior_names[h][name],name))
            away = min(prior_names[a],key=lambda name:(-prior_names[a][name],name))
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
            "duplicate_history_observations": exact_history_duplicates,
            "conflicting_native_id_observations": blocked_native_rows,
            "conflicting_kickoff_pairs": clock_conflict_pairs,
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
