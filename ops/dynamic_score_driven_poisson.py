"""Original score-driven dynamic Poisson research challenger (NOT Bayesian).

Model team attack and defense as evolving log-strength states. After every
historical full-time score becomes available, update only its four involved
team states using bounded Poisson score residuals. Strengths decay toward
zero with calendar time. The NEXT match uses strictly earlier observed goals.

This is a fixed-hyperparameter research hypothesis, not proven superior. No
external fetching, bookmaker prices, signed timestamps, betting or deployment.
"""
import argparse
from collections import Counter
from datetime import datetime, date, timezone, timedelta
import json
import math

from .penaltyblog_research_bridge import (
    SCHEMA as BRIDGE_SCHEMA, _timestamp, _validate, _unique_json,
)
from .penaltyblog_bivariate_goals_challenger import (
    _markets, MAX_GOALS,
)

SCHEMA = "football-king-dynamic-score-poisson-offline-v1"
MODEL_ID = "dynamic-score-driven-poisson-fixed-eta-0035-decay180-v1"
PRIOR_GAMES = 30
PRIOR_HOME_GOALS = 1.35
PRIOR_AWAY_GOALS = 1.10
LEARNING_RATE = 0.035
HALF_LIFE_DAYS = 180.0
MAX_STATE = 1.25
MIN_RATE, MAX_RATE = 0.08, 6.5
MAX_EVENTS = 2500


def _hold(reason, **extra):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "production_recommendations": "DISABLED", "positive_ev_verified": False,
        "model_promoted": False, "verified_forward_samples": 0,
        "source_authenticity_verified": False,
        "result_publication_time_independently_verified": False,
        "independent_timestamp_attestation": False,
        "real_bookmaker_quotes_verified": False,
        **extra,
    }


def _clamp(value, lower, upper):
    return min(upper, max(lower, value))


def _safe_rate(base, attack, defense):
    return _clamp(base * math.exp(attack + defense), MIN_RATE, MAX_RATE)


def _poisson_mass(rate):
    mass = [math.exp(-rate)]
    for score in range(1, MAX_GOALS):
        mass.append(mass[-1] * rate / score)
    # The last goal bucket represents >= (MAX_GOALS-1). This slight tail
    # approximation is shared by ALL derived markets, which stay coherent.
    mass[-1] += max(0.0, 1.0 - sum(mass))
    return mass


def score_grid(home_rate, away_rate):
    if (type(home_rate) not in (int, float)
            or type(away_rate) not in (int, float)
            or not all(math.isfinite(x) and MIN_RATE <= x <= MAX_RATE
                       for x in (home_rate, away_rate))):
        raise ValueError("INVALID_DYNAMIC_GOAL_RATES")
    home = _poisson_mass(home_rate)
    away = _poisson_mass(away_rate)
    matrix = [[h * a for a in away] for h in home]
    total = sum(sum(row) for row in matrix)
    if not 0.999999999 <= total <= 1.000000001:
        raise ValueError("INVALID_DYNAMIC_SCORE_MASS")
    p3 = [
        sum(matrix[h][a] for h in range(MAX_GOALS) for a in range(MAX_GOALS) if h > a),
        sum(matrix[h][h] for h in range(MAX_GOALS)),
        sum(matrix[h][a] for h in range(MAX_GOALS) for a in range(MAX_GOALS) if h < a),
    ]
    return {
        "p_home_draw_away": [round(x, 12) for x in p3],
        "over_total_goals_settlement": _markets(matrix, "over", (2.5, 2.75, 3.0)),
        "home_asian_handicap_settlement": _markets(
            matrix, "home_handicap", (-0.75, -0.5, -0.25, 0.0, 0.25)),
    }


def _fit(events, as_of, target_home, target_away):
    """Events are (match_kickoff_datetime, home_id, away_id, HG, AG).

    The caller FIRST checks every result was actually received before cutoff.
    Eligible games must update team states in chronological PLAYED order,
    not falsely place all old games at a single source-response fetch time.
    Kickoff times are caller-provided, not independently attested.
    """
    if (not 30 <= len(events) <= MAX_EVENTS
            or not isinstance(as_of, datetime)
            or as_of.tzinfo is None):
        raise ValueError("INSUFFICIENT_OR_INVALID_HISTORY")
    attack, defense, updated = {}, {}, {}
    appearances = Counter()
    total_h, total_a, n = PRIOR_GAMES * PRIOR_HOME_GOALS, PRIOR_GAMES * PRIOR_AWAY_GOALS, PRIOR_GAMES
    last_time = None

    def strength(team, current):
        age = (current - updated.get(team, current)).total_seconds() / 86400
        if age < -1e-9:
            raise ValueError("HISTORY_NOT_TIME_SORTED")
        decay = math.exp(-math.log(2) * max(age, 0.0) / HALF_LIFE_DAYS)
        return (attack.get(team, 0.0) * decay,
                defense.get(team, 0.0) * decay)

    for when, home, away, hg, ag in events:
        if (type(when) is not datetime or when.tzinfo is None
                or not when < as_of or (last_time is not None and when < last_time)
                or type(home) is not str or not home
                or type(away) is not str or not away or home == away
                or type(hg) is not int or type(ag) is not int
                or not 0 <= hg <= 20 or not 0 <= ag <= 20):
            raise ValueError("INVALID_DYNAMIC_HISTORY_OR_TIME")
        last_time = when
        home_a, home_d = strength(home, when)
        away_a, away_d = strength(away, when)
        base_h = total_h / n
        base_a = total_a / n
        expected_h = _safe_rate(base_h, home_a, away_d)
        expected_a = _safe_rate(base_a, away_a, home_d)
        # Stable Poisson score-driven updates; eta & clipping fixed BEFORE OOS.
        residual_h = _clamp(
            (hg - expected_h) / max(1.0, math.sqrt(expected_h)), -2.5, 2.5)
        residual_a = _clamp(
            (ag - expected_a) / max(1.0, math.sqrt(expected_a)), -2.5, 2.5)
        attack[home] = _clamp(home_a + LEARNING_RATE * residual_h, -MAX_STATE, MAX_STATE)
        defense[away] = _clamp(away_d + LEARNING_RATE * residual_h, -MAX_STATE, MAX_STATE)
        attack[away] = _clamp(away_a + LEARNING_RATE * residual_a, -MAX_STATE, MAX_STATE)
        defense[home] = _clamp(home_d + LEARNING_RATE * residual_a, -MAX_STATE, MAX_STATE)
        updated[home] = updated[away] = when
        appearances.update((home, away))
        total_h += hg
        total_a += ag
        n += 1
    if min(appearances[target_home], appearances[target_away]) < 5:
        raise ValueError("TARGET_TEAMS_NOT_TRAINED")
    h_a, _ = strength(target_home, as_of)
    _, a_d = strength(target_away, as_of)
    a_a, _ = strength(target_away, as_of)
    _, h_d = strength(target_home, as_of)
    return (_safe_rate(total_h / n, h_a, a_d),
            _safe_rate(total_a / n, a_a, h_d))


def predict_offline(payload):
    """Authenticity not established even if chronology and math are valid."""
    if (type(payload) is not dict
            or set(payload) != {"schema", "production_recommendations", "as_of_utc",
                                "target_fixture", "historical_matches"}
            or payload.get("schema") != SCHEMA
            or payload.get("production_recommendations") != "DISABLED"):
        return _hold("INVALID_RESEARCH_CONTRACT")
    validation = {
        **payload, "schema": BRIDGE_SCHEMA, "model": "poisson",
    }
    try:
        target, history = _validate(validation)
        cutoff = _timestamp(payload["as_of_utc"])
        # _validate has already required result_recorded_utc <= as_of_utc
        # and historical kickoff strictly before target as_of. In a live
        # same-GET capture every old result may have the SAME local first-
        # observed timestamp; that is NOT when the game was played. Evolve
        # match strength in actual kickoff order while admitting only scores
        # whose results are known by the target cutoff.
        events = sorted([
            (_timestamp(r["kickoff_utc"]),
             r["home_team_id"], r["away_team_id"],
             r["home_goals"], r["away_goals"])
            for r in history], key=lambda x: x[0])
        home_rate, away_rate = _fit(
            events, cutoff, target["home_team_id"], target["away_team_id"])
        grid = score_grid(home_rate, away_rate)
        return _hold(
            "UNVERIFIED_DYNAMIC_POISSON_RESEARCH_ONLY",
            model_id=MODEL_ID,
            source_namespace=target["source_namespace"],
            league_id=target["league_id"], fixture_id=target["event_id"],
            kickoff_utc=target["kickoff_utc"], as_of_utc=payload["as_of_utc"],
            training_match_count=len(history),
            hyperparameters_fixed_not_optimized={
                "learning_rate": LEARNING_RATE,
                "strength_half_life_days": HALF_LIFE_DAYS,
                "prior_games": PRIOR_GAMES,
                "prior_home_goals": PRIOR_HOME_GOALS,
                "prior_away_goals": PRIOR_AWAY_GOALS,
            },
            expected_home_goals=round(home_rate, 8),
            expected_away_goals=round(away_rate, 8),
            **grid,
        )
    except (ValueError, TypeError, KeyError, OverflowError):
        return _hold("INVALID_OR_UNAVAILABLE_DYNAMIC_MODEL_HISTORY")


def date_only_diagnostic_rates(train, target_home, target_away, cutoff_day):
    """Retrospective exploratory ONLY. Source dates are NOT UTC receipt proof.

    Used to compare the old inspected 2025/2026 score cohort without
    inventing first-publication times. Match-date-only records are sorted by
    calendar date; no test outcomes may be supplied in train.
    """
    if (type(cutoff_day) is not date or
            not isinstance(train, list)):
        raise ValueError("INVALID_RETROSPECTIVE_CUTOFF")
    events = []
    for row in train:
        if type(row) is not dict:
            raise ValueError("INVALID_DATE_ONLY_ROW")
        date_value = row.get("date")
        if type(date_value) is not str:
            raise ValueError("INVALID_DATE_ONLY_ROW")
        day = date.fromisoformat(date_value)
        if day.isoformat() != date_value or not day < cutoff_day:
            raise ValueError("LOOKAHEAD_IN_DATE_ONLY_REPLAY")
        goals = row.get("score_ft")
        if type(goals) is not list or len(goals) != 2:
            raise ValueError("INVALID_DATE_ONLY_SCORE")
        # Ordinal calendar-day ordering ONLY; not observed publisher timestamps.
        events.append((
            datetime(day.year, day.month, day.day, tzinfo=timezone.utc),
            row.get("home"), row.get("away"), goals[0], goals[1],
        ))
    events.sort(key=lambda x: x[0])
    cutoff = datetime(cutoff_day.year, cutoff_day.month, cutoff_day.day,
                      tzinfo=timezone.utc)
    return _fit(events, cutoff, target_home, target_away)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    args = parser.parse_args(argv)
    with open(args.input, encoding="utf-8") as fh:
        payload = json.load(
            fh, object_pairs_hook=_unique_json,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")),
        )
    print(json.dumps(predict_offline(payload), ensure_ascii=False,
                     indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
