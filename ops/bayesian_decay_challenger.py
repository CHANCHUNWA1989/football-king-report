"""Research-only Gamma-Poisson empirical-prior / time-decay strength challenger.

One shadow candidate per eligible ORIGINAL snapshot fixture. It never edits the
old model or seals a prediction. Date-only match results are NOT authenticated
against the provider and an injected analysis clock is NOT an external witness.
This is an empirical-Bayes-style power-likelihood heuristic, not a fitted
hierarchical Bayesian league model or evidence of improved out-of-sample play.
"""
from collections import defaultdict
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
import math

from shadow_forecast import LEAGUES, predict_league, poisson_1x2

HK = ZoneInfo("Asia/Hong_Kong")
MODEL = "gamma-poisson-time-decay-strength-research-v1"
HALF_LIFE_DAYS = 120
PRIOR_EXPOSURE = 8
MIN_RECENCY_WEIGHTED_GAMES = 12.0
MAX_ROWS = 6000


def _result():
    return {
        "schema": "football-king-gamma-poisson-decay-research-v1",
        "model": MODEL, "status": "HOLD", "reason": "INVALID_INPUT",
        "candidate_count": 0, "comparisons": [],
        "half_life_days": HALF_LIFE_DAYS,
        "prior_exposure_matches": PRIOR_EXPOSURE,
        "training_date_policy": "STRICTLY_BEFORE_HK_AS_OF_DAY",
        "original_shadow_unchanged": True,
        "original_forecasts_resigned_or_rewritten": False,
        "analysis_clock_is_supplied_not_attested": True,
        "source_fixtures_authenticated": False,
        "forecast_capture_attested": False,
        "actual_score_sources_independently_verified": False,
        "official_xg_available": False,
        "real_bookmaker_quotes_verified": False,
        "probabilities_calibrated": False,
        "positive_ev_verified": False,
        "eligible_for_formal_forward_scoring": False,
        "published_recommendations_enabled": False,
        "production_recommendations": "DISABLED",
    }


def _row_history(rows, today, now):
    """Mirror legacy source history admission and collapse equal duplicate rows."""
    cases = {}
    by_event = {}
    for row in rows:
        if type(row) is not dict:
            continue
        home, away = row.get("home"), row.get("away")
        if (type(home) is not str or not home or len(home) >= 110
                or type(away) is not str or not away or len(away) >= 110
                or home == away or row.get("status") != "FINISHED"):
            continue
        try:
            day = date.fromisoformat(row["date"])
        except (KeyError, ValueError, TypeError):
            continue
        if day >= today:
            continue
        score = row.get("score_ft")
        if (type(score) is not list or len(score) != 2
                or any(type(n) is not int or not 0 <= n <= 20 for n in score)):
            continue
        claimed_kickoff = row.get("kickoff_utc")
        if claimed_kickoff is not None:
            if type(claimed_kickoff) is not str or len(claimed_kickoff) > 45:
                raise ValueError("HISTORICAL_KICKOFF_TIME_CONFLICT")
            try:
                clock = datetime.fromisoformat(claimed_kickoff.replace("Z", "+00:00"))
                if (clock.tzinfo is None or clock.utcoffset() is None
                        or clock.astimezone(HK).date() != day or clock >= now):
                    raise ValueError("HISTORICAL_KICKOFF_TIME_CONFLICT")
            except (ValueError, OverflowError):
                raise ValueError("HISTORICAL_KICKOFF_TIME_CONFLICT") from None
        key = (day.isoformat(), home, away)
        value = (score[0], score[1])
        if key in cases and cases[key] != value:
            raise ValueError("CONFLICTING_HISTORICAL_RESULT")
        cases[key] = value
        event_id = row.get("event_id")
        if event_id is not None:
            if (type(event_id) is not str or not event_id.strip()
                    or event_id != event_id.strip() or len(event_id) > 128):
                raise ValueError("INVALID_HISTORY_SOURCE_EVENT_ID")
            signature = (key, value)
            if event_id in by_event and by_event[event_id] != signature:
                raise ValueError("CONFLICTING_HISTORY_SOURCE_EVENT_ID")
            by_event[event_id] = signature
    return sorted((date.fromisoformat(day), home, away, *score)
                  for (day, home, away), score in cases.items())


def _posterior(roles, team, field, league_baseline):
    """Gamma prior has pseudo-exposure=8 and mean=league role baseline."""
    weighted = roles[(team, field)]
    exposure = math.fsum(weight for weight, _ in weighted)
    shape = PRIOR_EXPOSURE * league_baseline + math.fsum(
        weight * goals for weight, goals in weighted)
    rate = PRIOR_EXPOSURE + exposure
    return (shape / rate, math.sqrt(shape) / rate)


def _normalize_history(history, today):
    weights = [math.exp2(-(today - day).days / HALF_LIFE_DAYS)
               for day, _, _, _, _ in history]
    weighted_games = math.fsum(weights)
    if weighted_games < MIN_RECENCY_WEIGHTED_GAMES:
        raise ValueError("INSUFFICIENT_RECENCY_WEIGHTED_HISTORY")
    # Distinct historically finished matches; not forecasts or attestations.
    home_baseline = max(.3, math.fsum(
        w * gh for w, (_, _, _, gh, _) in zip(weights, history)) / weighted_games)
    away_baseline = max(.3, math.fsum(
        w * ga for w, (_, _, _, _, ga) in zip(weights, history)) / weighted_games)
    roles = defaultdict(list)
    team_appearances = defaultdict(int)
    for w, (_, home, away, gh, ga) in zip(weights, history):
        team_appearances[home] += 1
        team_appearances[away] += 1
        roles[(home, "home_for")].append((w, gh))
        roles[(home, "home_against")].append((w, ga))
        roles[(away, "away_for")].append((w, ga))
        roles[(away, "away_against")].append((w, gh))
    return roles, team_appearances, home_baseline, away_baseline, weighted_games


def _explicit_scheduled_match(rows, baseline):
    """Never infer a source ID from team names, time, or the legacy fallback."""
    found = [row for row in rows if type(row) is dict
             and row.get("event_id") == baseline["event_id"]]
    return (len(found) == 1 and
            type(found[0].get("event_id")) is str
            and 0 < len(found[0]["event_id"]) <= 128
            and found[0].get("status") == "SCHEDULED"
            and found[0].get("score_ft") is None
            and all(found[0].get(k) == baseline.get(k) for k in
                    ("home", "away", "kickoff_utc")))


def compare_shadow(rows, *, league, now):
    """Pair old and new forecasts from identical source rows at one model clock.

    A simulated date-clock may be used for synthetic testing, but output never
    calls itself a sealed authentic prediction. Do not use in production bets.
    """
    if (not isinstance(now, datetime) or now.tzinfo is None
            or now.utcoffset() is None):
        raise ValueError("NAIVE_OR_INVALID_MODEL_CLOCK")
    out = _result()
    out["as_of_utc_self_declared"] = now.astimezone(timezone.utc).isoformat()
    if league not in LEAGUES or type(league) is not str:
        out["reason"] = "LEAGUE_NOT_IN_ORIGINAL_SHADOW"
        return out
    if type(rows) is not list or len(rows) > MAX_ROWS:
        out["reason"] = "INVALID_OR_OVERSIZED_INPUT"
        return out
    try:
        original = predict_league(rows, league, now)
    except (ValueError, TypeError, KeyError, OverflowError):
        out["reason"] = "LEGACY_SHADOW_COHORT_REJECTED"
        return out
    if not original:
        out["reason"] = "NO_ELIGIBLE_ORIGINAL_SHADOW_FIXTURE"
        return out
    today = now.astimezone(HK).date()
    try:
        history = _row_history(rows, today, now)
        (roles, appearances, league_home, league_away,
         exposure) = _normalize_history(history, today)
    except (ValueError, TypeError, OverflowError) as error:
        reason = str(error)
        out["reason"] = reason if reason in (
            "INSUFFICIENT_RECENCY_WEIGHTED_HISTORY",
            "CONFLICTING_HISTORICAL_RESULT",
            "HISTORICAL_KICKOFF_TIME_CONFLICT",
            "INVALID_HISTORY_SOURCE_EVENT_ID",
            "CONFLICTING_HISTORY_SOURCE_EVENT_ID") else "INVALID_HISTORY"
        return out
    out["training_original_distinct_games"] = len(history)
    out["training_effective_exposure_games"] = round(exposure, 6)
    # These two hyperparameters were chosen a priori for research, never fit
    # using this fixture's actual result or the user's proposed bet.
    candidates = []
    for baseline in original:
        if not _explicit_scheduled_match(rows, baseline):
            continue
        home, away = baseline["home"], baseline["away"]
        if (appearances[home] < 3 or appearances[away] < 3
                or baseline.get("training_games") != len(history)
                or baseline.get("production_recommendations") != "DISABLED"
                or baseline.get("calibrated") is not False):
            continue
        h_atk, h_atk_sd = _posterior(roles, home, "home_for", league_home)
        a_def, a_def_sd = _posterior(roles, away, "away_against", league_home)
        a_atk, a_atk_sd = _posterior(roles, away, "away_for", league_away)
        h_def, h_def_sd = _posterior(roles, home, "home_against", league_away)
        lambda_home = min(5.5, max(.1, h_atk * a_def / league_home))
        lambda_away = min(5.5, max(.1, a_atk * h_def / league_away))
        p = poisson_1x2(lambda_home, lambda_away)
        candidates.append({
            "event_id_unverified": baseline["event_id"],
            "league": league, "home": home, "away": away,
            "kickoff_utc_source_claim": baseline["kickoff_utc"],
            "model_as_of_utc_self_declared": now.astimezone(timezone.utc).isoformat(),
            "original_shadow": {
                "model": baseline["model"],
                "p_home": baseline["p_home"],
                "p_draw": baseline["p_draw"],
                "p_away": baseline["p_away"],
            },
            "candidate": {
                "model": MODEL,
                "p_home": p[0], "p_draw": p[1], "p_away": p[2],
                "expected_home_goals": round(lambda_home, 5),
                "expected_away_goals": round(lambda_away, 5),
                "component_posterior_sd_theoretical_not_calibrated": {
                    "home_attack": round(h_atk_sd, 6),
                    "away_defense": round(a_def_sd, 6),
                    "away_attack": round(a_atk_sd, 6),
                    "home_defense": round(h_def_sd, 6),
                },
            },
            "same_source_rows_same_illustrative_clock": True,
            "original_sealed_predictions_modified": False,
            "forward_attested": False,
            "result_available_at_model_time": False,
            "model_calibrated": False,
            "ready_to_bet": False,
            "production_recommendations": "DISABLED",
        })
    if not candidates:
        out["reason"] = "NO_ELIGIBLE_EXPLICIT_FIXTURE_IDENTITY"
        return out
    out["candidate_count"] = len(candidates)
    out["comparisons"] = candidates
    out["status"] = "RESEARCH_ONLY"
    out["reason"] = "UNATTESTED_SAME_INPUT_MODEL_PAIR"
    return out
