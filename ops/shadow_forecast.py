"""Generate reproducible, **uncalibrated**, no-odds 1X2 shadow probabilities.

The only training inputs are finished results from prior local calendar days,
never future fixture scores. Outputs are research observations, not bets.
"""
import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HK = ZoneInfo("Asia/Hong_Kong")
LEAGUES = ("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1")


def poisson_1x2(home_rate, away_rate):
    if not all(math.isfinite(x) and 0.1 <= x <= 5.5 for x in (home_rate, away_rate)):
        raise ValueError("MODEL_RATE_OUT_OF_RANGE")
    h = [math.exp(-home_rate) * home_rate**i / math.factorial(i) for i in range(12)]
    a = [math.exp(-away_rate) * away_rate**i / math.factorial(i) for i in range(12)]
    values = [0.0, 0.0, 0.0]
    for i, hi in enumerate(h):
        for j, aj in enumerate(a):
            values[0 if i > j else 1 if i == j else 2] += hi * aj
    total = sum(values)
    return [round(x / total, 7) for x in values]


def _utc(s):
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("NAIVE_KICKOFF")
    return dt.astimezone(timezone.utc)


def predict_league(rows, league, now):
    """Return only genuinely pre-kickoff fixtures, with training data prior to today."""
    today = now.astimezone(HK).date()
    history, scheduled = [], []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        h, a = row.get("home"), row.get("away")
        if not all(isinstance(t, str) and t and len(t) < 110 for t in (h, a)) or h == a:
            continue
        try:
            match_day = date.fromisoformat(row["date"])
        except (KeyError, ValueError, TypeError):
            continue
        score = row.get("score_ft")
        if (match_day < today and row.get("status") == "FINISHED"
                and isinstance(score, list) and len(score) == 2
                and all(type(x) is int and 0 <= x <= 20 for x in score)):
            history.append((match_day, h, a, score[0], score[1]))
        kickoff = row.get("kickoff_utc")
        if not kickoff or score is not None or row.get("status") != "SCHEDULED":
            continue
        try:
            dt = _utc(kickoff)
        except (ValueError, TypeError):
            continue
        if (dt.astimezone(HK).date() != match_day
                or not (now + timedelta(minutes=10) < dt)
                or match_day > today + timedelta(days=21)):
            continue
        event_id = str(row.get("event_id") or league + "|" + match_day.isoformat() + "|" + h + "|" + a)
        if event_id in seen:
            continue
        seen.add(event_id)
        scheduled.append((dt, event_id, h, a, row.get("schedule_utc_source")))
    if len(history) < 30:
        return []
    team_appearances = defaultdict(int)
    home_for = defaultdict(list)
    away_for = defaultdict(list)
    for _, h, a, gh, ga in history:
        team_appearances[h] += 1
        team_appearances[a] += 1
        home_for[h].append((gh, ga))
        away_for[a].append((ga, gh))
    league_home = max(0.3, sum(r[3] for r in history) / len(history))
    league_away = max(0.3, sum(r[4] for r in history) / len(history))
    raw_history = json.dumps(sorted(history), ensure_ascii=False, default=str).encode("utf-8")
    digest = hashlib.sha256(raw_history).hexdigest()
    predictions = []
    prior = 6
    for ko, event_id, h, a, schedule_source in sorted(scheduled):
        if team_appearances[h] < 3 or team_appearances[a] < 3:
            continue
        def mean_role(team, group, i, average):
            values = group[team]
            return (sum(x[i] for x in values) + prior * average) / (len(values) + prior)
        h_attack = mean_role(h, home_for, 0, league_home)
        a_defense = mean_role(a, away_for, 1, league_home)
        a_attack = mean_role(a, away_for, 0, league_away)
        h_defense = mean_role(h, home_for, 1, league_away)
        expected_home = min(5.5, max(0.1, h_attack * a_defense / league_home))
        expected_away = min(5.5, max(0.1, a_attack * h_defense / league_away))
        probabilities = poisson_1x2(expected_home, expected_away)
        predictions.append({
            "league": league, "event_id": event_id, "home": h, "away": a,
            "kickoff_utc": ko.isoformat(), "prediction_utc": now.isoformat(),
            "model": "poisson-shrinkage-unvalidated-v4.1",
            "training_games": len(history), "training_cutoff_local_day": today.isoformat(),
            "training_observations_sha256": digest,
            "p_home": probabilities[0], "p_draw": probabilities[1], "p_away": probabilities[2],
            "expected_home_goals": round(expected_home, 5),
            "expected_away_goals": round(expected_away, 5),
            "schedule_utc_source": schedule_source or "original_fixture_gateway",
            "schedule_time_agreement_only_not_result_verification": bool(schedule_source),
            "calibrated": False, "verified_market_odds": False,
            "production_recommendations": "DISABLED",
        })
    return predictions


def generate(now=None, getter=None, *, return_finished=False,
             secondary_snapshot=None, market_schedule=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    # Pure unit tests may supply a fake source without the separately unpacked V4.1 app.
    if getter is None:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
        from fixture_gateway import get_fixtures
        getter = get_fixtures
    local = now.astimezone(HK)
    start_year = local.year if local.month >= 7 else local.year - 1
    season = f"{start_year}-{(start_year+1)%100:02d}"
    predictions, sources = [], []
    enrichment_total = 0
    agreement_total = 0
    finished_observations = []
    for league in LEAGUES:
        try:
            raw = getter(season=season, league=league, clock=lambda: now)
            data = raw.get("matches", [])
            if raw.get("status") != "READY_RESEARCH" or not isinstance(data, list):
                raise ValueError("NO_PUBLIC_SEASON_RESULTS")
            enrichment = {}
            if secondary_snapshot is not None and market_schedule is not None:
                from schedule_enrichment import enrich
                data, enrichment = enrich(data, league, secondary_snapshot, market_schedule, now)
                enrichment_total += (
                    enrichment["updated_existing_schedules"]
                    + enrichment["added_crosschecked_schedules"]
                )
                agreement_total += enrichment["source_time_agreements"]
            preds = predict_league(data, league, now)
            predictions.extend(preds)
            if return_finished:
                for event in data:
                    if not isinstance(event,dict) or event.get("status")!="FINISHED":
                        continue
                    score=event.get("score_ft")
                    if (not isinstance(score,list) or len(score)!=2
                            or not all(type(x) is int and 0<=x<=20 for x in score)):
                        continue
                    home,away=event.get("home"),event.get("away")
                    if not all(isinstance(t,str) and t for t in (home,away)):
                        continue
                    finished_observations.append({
                        "league":league,"home":home,"away":away,
                        "date":event.get("date"),
                        "kickoff_utc":event.get("kickoff_utc"),
                        "score_ft":score,"status":"FINISHED",
                        "source":raw.get("source"),
                        "source_url":raw.get("source_url"),
                    })
            sources.append({
                "league": league, "source": raw.get("source"), "source_url": raw.get("source_url"),
                "status": "READY_RESEARCH", "training_and_candidate_source_unverified": True,
                "predictions": len(preds), "season": season,
                "secondary_schedule_utc_enriched": (
                    enrichment.get("updated_existing_schedules", 0)
                    + enrichment.get("added_crosschecked_schedules", 0)
                ),
                "two_source_confirmed_schedule_restorations": enrichment.get(
                    "added_crosschecked_schedules", 0),
                "secondary_market_fixture_utc_agreements": enrichment.get("source_time_agreements", 0),
                "secondary_schedule_audit": {
                    key: enrichment.get(key, 0) for key in (
                        "secondary_scheduled", "gateway_scheduled_fixture_keys",
                        "unmatched_gateway_fixture_keys",
                        "unmatched_market_fixture_keys",
                        "calendar_date_conflicts")
                },
                "captured_utc": raw.get("captured_utc"),
                "upstream_updated_utc": raw.get("upstream_updated_utc"),
            })
        except (ValueError, TypeError, OSError, OverflowError, KeyError) as exc:
            sources.append({"league": league, "status": "HOLD", "reason": type(exc).__name__,
                            "predictions": 0})
    predictions.sort(key=lambda row: (row["kickoff_utc"], row["league"], row["event_id"]))
    output = {
        "schema": "football-king-uncalibrated-shadow-1",
        "as_of_utc": now.isoformat(), "season": season,
        "status": "SHADOW_ONLY" if predictions else "HOLD",
        "predictions_count": len(predictions), "sources": sources,
        "predictions": predictions,
        "additional_precise_schedule_utc": enrichment_total,
        "independent_schedule_market_time_agreements": agreement_total,
        "secondary_schedule_sources_only_not_model_odds": True,
        "lineups_confirmed": False, "xg_verified": False,
        "market_odds_available": False, "model_calibrated": False,
        "independently_verified_results": False,
        "production_recommendations": "DISABLED",
        "warning": "Model output is uncalibrated research, not betting recommendations or proof of profitability.",
    }
    if return_finished:
        output["_internal_finished_results"] = {
            "schema":"football-king-single-source-finished-results-1",
            "captured_utc":now.isoformat(),
            "records":finished_observations,
            "independently_verified_all_leagues":False,
            "production_recommendations":"DISABLED",
        }
    return output


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    p.add_argument("--finished-output", default=None)
    p.add_argument("--secondary", default="sources/latest.json")
    p.add_argument("--market-schedule", default="market/latest.json")
    args = p.parse_args()
    def safe_read(path):
        try:
            obj = json.loads(Path(path).read_text(encoding="utf-8"))
            return obj if isinstance(obj, dict) else None
        except (OSError, UnicodeError, ValueError):
            return None
    result = generate(return_finished=bool(args.finished_output),
                      secondary_snapshot=safe_read(args.secondary),
                      market_schedule=safe_read(args.market_schedule))
    internal = result.pop("_internal_finished_results", None)
    if args.finished_output:
        location = Path(args.finished_output)
        location.parent.mkdir(parents=True,exist_ok=True)
        location.write_text(json.dumps(internal,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "predictions": result["predictions_count"],
                      "source_results": result["sources"],
                      "production_recommendations": "DISABLED"}, ensure_ascii=False))
