"""Exact quarter-line Asian handicap settlement and Poisson scenario analysis.

This research-only module does NOT identify a bookmaker's actually offered
handicap, offered decimal odds, live score, value bet or historical ROI.
Any scenario line is HYPOTHETICAL unless accompanied by independently verified,
time-sealed market odds. Never use the results to enable live betting.
"""
import math
from decimal import Decimal, InvalidOperation

SCHEMA = "football-king-asian-handicap-research-v1"
TYPES = ("FULL_WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "FULL_LOSS")
MAX_GOALS = 24
MAX_EXPECTED_GOALS = 5.5


def quarter_units(handicap):
    """Parse a genuine quarter-goal line without accidental float rounding."""
    if isinstance(handicap, bool) or not isinstance(handicap, (float, int, str, Decimal)):
        raise ValueError("BAD_HANDICAP")
    try:
        number = Decimal(str(handicap))
    except InvalidOperation as exc:
        raise ValueError("BAD_HANDICAP") from exc
    if not number.is_finite() or number < -5 or number > 5:
        raise ValueError("HANDICAP_OUT_OF_RESEARCH_RANGE")
    units = number * 4
    if units != units.to_integral_value():
        raise ValueError("NOT_A_QUARTER_GOAL")
    return int(units)


def split_lines(handicap):
    """Represent split stakes in quarter-goal integer units."""
    units = quarter_units(handicap)
    if units % 2 == 0:
        return (units, units)
    return (units - 1, units + 1)


def grade(home_goals, away_goals, side, handicap):
    """Grade a 90-minute FT score. Side owns the handicap, not 'home' by default."""
    if (type(home_goals) is not int or type(away_goals) is not int
            or not 0 <= home_goals <= 25 or not 0 <= away_goals <= 25):
        raise ValueError("BAD_FINAL_GOALS")
    if side not in ("HOME", "AWAY"):
        raise ValueError("BAD_MARKET_SIDE")
    score_difference = (home_goals - away_goals) if side == "HOME" else (away_goals - home_goals)
    halves = []
    for quarter in split_lines(handicap):
        adjusted_quarters = 4 * score_difference + quarter
        halves.append(1 if adjusted_quarters > 0 else -1 if adjusted_quarters < 0 else 0)
    net = sum(halves)
    return {2: "FULL_WIN", 1: "HALF_WIN", 0: "PUSH",
            -1: "HALF_LOSS", -2: "FULL_LOSS"}[net]


def _poisson(goal_rate):
    if (type(goal_rate) not in (int, float) or not math.isfinite(goal_rate)
            or not .10 <= goal_rate <= MAX_EXPECTED_GOALS):
        raise ValueError("INVALID_EXPECTED_GOALS")
    terms = [math.exp(-goal_rate)]
    for n in range(1, MAX_GOALS + 1):
        terms.append(terms[-1] * goal_rate / n)
    total = sum(terms)
    if total <= 0:
        raise ValueError("IMPOSSIBLE_POISSON_TOTAL")
    return [v / total for v in terms]


def probabilities(expected_home_goals, expected_away_goals, side, handicap):
    """Five-grade scenario probabilities from two *independent* Poisson rates.

    Reliability of the Poisson assumption has NOT been verified for Japan J1.
    Returned 'neutral_price' is only a model-implied algebraic threshold, not
    a bookmaker quote or real betting advantage.
    """
    split_lines(handicap)
    if side not in ("HOME", "AWAY"):
        raise ValueError("BAD_MARKET_SIDE")
    home = _poisson(expected_home_goals)
    away = _poisson(expected_away_goals)
    out = {key: 0.0 for key in TYPES}
    for h, ph in enumerate(home):
        for a, pa in enumerate(away):
            out[grade(h, a, side, handicap)] += ph * pa
    if abs(sum(out.values()) - 1) > 1e-8:
        raise ValueError("INVALID_TOTAL_PROBABILITY")
    weighted_win = out["FULL_WIN"] + out["HALF_WIN"] / 2
    weighted_loss = out["FULL_LOSS"] + out["HALF_LOSS"] / 2
    neutral = 1 + weighted_loss / weighted_win if weighted_win > 0 else None
    return {
        "schema": SCHEMA, "side": side, "hypothetical_handicap": float(Decimal(str(handicap))),
        "outcome_probabilities": {key: round(out[key], 7) for key in TYPES},
        "full_or_half_win_probability": round(weighted_win * 0 + out["FULL_WIN"] + out["HALF_WIN"], 7),
        "non_loss_probability_including_push": round(
            out["FULL_WIN"] + out["HALF_WIN"] + out["PUSH"], 7),
        "model_implied_neutral_decimal_price_not_a_quote": (
            round(neutral, 5) if neutral is not None else None),
        "poisson_model_is_uncalibrated": True,
        "offered_handicap_line_authenticated": False,
        "offered_decimal_odds_authenticated": False,
        "positive_expected_value_verified": False,
        "qualifies_for_betting": False,
        "production_recommendations": "DISABLED",
    }


def summarize_scenario(replay_rows, side, handicap):
    """Score the SAME hypothetical market line on every past fixture.

    A fixed-line scenario cannot establish actual historical '下盤' returns:
    actual sportsbook favourite/underdog lines and odds are absent.
    """
    split_lines(handicap)
    counts = {key: 0 for key in TYPES}
    predicted = {key: 0.0 for key in TYPES}
    used = 0
    for row in replay_rows:
        if not isinstance(row, dict):
            continue
        try:
            gh, ga = row["score_ft"]
            h, a = row["expected_home_goals"], row["expected_away_goals"]
            actual = grade(gh, ga, side, handicap)
            dist = probabilities(h, a, side, handicap)["outcome_probabilities"]
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
        counts[actual] += 1
        for key in TYPES:
            predicted[key] += dist[key]
        used += 1
    if not used:
        return {
            "n": 0, "status": "HOLD",
            "reason": "NO_REPLAYABLE_PREVIOUS_DAY_PREDICTIONS",
            "actual_market_lines_observed": False,
            "odds_and_roi_available": False,
            "production_recommendations": "DISABLED",
        }
    def observed_frac(*categories):
        return round(sum(counts[c] for c in categories) / used, 5)
    return {
        "status": "RESEARCH_ONLY",
        "n": used, "side": side, "hypothetical_handicap": float(Decimal(str(handicap))),
        "observed_grades": counts,
        "observed_full_or_half_win_fraction": observed_frac("FULL_WIN", "HALF_WIN"),
        "observed_non_loss_fraction_including_push": observed_frac(
            "FULL_WIN", "HALF_WIN", "PUSH"),
        "mean_prior_date_model_grade_probabilities": {
            k: round(predicted[k] / used, 5) for k in TYPES
        },
        "same_fixed_line_on_every_fixture": True,
        "actual_market_lines_observed": False,
        "independent_as_of_prediction_archive_present": False,
        "bookmaker_closing_odds_available": False,
        "historical_roi_not_estimable": True,
        "betting_recommendation_count": 0,
        "production_recommendations": "DISABLED",
    }
