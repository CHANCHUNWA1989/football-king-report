"""Exact football goal-totals quarter-line EV arithmetic; unverified research only.

Use an integer total-goals probability distribution, NOT a 1X2 or binary
over/under probability. A quarter total splits the stake equally between
adjacent half-goal/integer lines. No model/calibration/quote provenance is
authenticated by these inputs, irrespective of caller-supplied flags.
"""
from decimal import Decimal, InvalidOperation
import math

from asian_ev_research import expected_value, asian_net
from value_ev_policy import (
    DEFAULT_MIN_DECIMAL_ODDS, DEFAULT_MIN_CONSERVATIVE_EV,
    MAX_QUOTE_AGE_SECONDS,
)

SCHEMA = "football-king-total-goals-ev-research-v1"
MAX_TOTAL_GOALS = 40
MAX_TOTAL_LINE = 15
GRADES = ("FULL_WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "FULL_LOSS")


def _number(value, minimum, maximum):
    return (type(value) in (int, float) and math.isfinite(value)
            and minimum <= value <= maximum)


def _line_units(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("INVALID_TOTAL_LINE")
    try:
        units = Decimal(str(value)) * 4
    except InvalidOperation as exc:
        raise ValueError("INVALID_TOTAL_LINE") from exc
    if not (1 <= units <= 4 * MAX_TOTAL_LINE
            and units == units.to_integral_value()):
        raise ValueError("INVALID_QUARTER_TOTAL_LINE")
    return int(units)


def _total_key(key):
    # Accept JSON integer keys ("0", "1", ...) without ambiguous aliases.
    if type(key) is int:
        n = key
    elif (type(key) is str and key.isascii() and key.isdecimal()
          and (key == "0" or not key.startswith("0"))):
        n = int(key)
    else:
        raise ValueError("INVALID_TOTAL_GOALS_KEY")
    if not 0 <= n <= MAX_TOTAL_GOALS:
        raise ValueError("TOTAL_GOALS_OUT_OF_RANGE")
    return n


def _distribution(value, *, original=None):
    if not isinstance(value, dict) or not 1 <= len(value) <= MAX_TOTAL_GOALS + 1:
        raise ValueError("MISSING_OR_INVALID_TOTAL_GOALS_DISTRIBUTION")
    out = {}
    for key, p in value.items():
        n = _total_key(key)
        if n in out:
            raise ValueError("DUPLICATE_TOTAL_GOALS_KEY")
        if not _number(p, 0, 1):
            raise ValueError("INVALID_TOTAL_GOALS_PROBABILITY")
        if original is not None and (n not in original or p > original[n]):
            raise ValueError("INVALID_CONSERVATIVE_TOTAL_LOWER_BOUNDS")
        out[n] = p
    total = math.fsum(out.values())
    if original is None:
        if abs(total - 1) > 1e-8:
            raise ValueError("TOTAL_GOALS_DISTRIBUTION_NOT_NORMALIZED")
    elif total > 1 + 1e-10:
        raise ValueError("INVALID_CONSERVATIVE_TOTAL_LOWER_BOUNDS")
    return out


def _grade(goals, side, units):
    halves = (units, units) if units % 2 == 0 else (units - 1, units + 1)
    net = 0
    for half in halves:
        diff = 4 * goals - half if side == "OVER" else half - 4 * goals
        net += int(diff > 0) - int(diff < 0)
    return {2: "FULL_WIN", 1: "HALF_WIN", 0: "PUSH",
            -1: "HALF_LOSS", -2: "FULL_LOSS"}[net]


def _profit(goals, side, units, decimal_odds):
    line = units / 4
    if side == "OVER":
        return asian_net(goals, -line, decimal_odds)
    return asian_net(-goals, line, decimal_odds)


def assess(goals_probabilities, *, side, line, decimal_odds=None,
           conservative_goal_lower_bounds=None, quote_age_seconds=None):
    """Hypothetical EV on a total-goals distribution; never authorizes a bet."""
    result = {
        "schema": SCHEMA,
        "status": "HOLD",
        "reason": "UNKNOWN",
        "research_value_screen_pass": False,
        "nominal_ev_per_unit_claimed_price": None,
        "conservative_ev_lower_bound_if_claims_valid": None,
        "five_grade_probabilities_unverified": None,
        "goal_distribution_independently_authenticated": False,
        "calibration_lower_bounds_independently_authenticated": False,
        "quote_executable_authenticated": False,
        "quote_timestamp_independently_authenticated": False,
        "positive_expected_value_verified": False,
        "can_enter_formal_settlement_ledger": False,
        "formal_bet_count": 0,
        "recommended_stake": None,
        "production_recommendations": "DISABLED",
        "minimum_decimal_odds": DEFAULT_MIN_DECIMAL_ODDS,
        "minimum_conservative_ev": DEFAULT_MIN_CONSERVATIVE_EV,
        "max_quote_age_seconds": MAX_QUOTE_AGE_SECONDS,
    }
    if side not in ("OVER", "UNDER"):
        result["reason"] = "INVALID_TOTAL_DIRECTION"
        return result
    try:
        units = _line_units(line)
    except (ValueError, TypeError, OverflowError) as exc:
        result["reason"] = str(exc)
        return result
    if goals_probabilities is None:
        result["reason"] = "NEEDS_FULL_TOTAL_GOAL_DISTRIBUTION"
        return result
    try:
        distribution = _distribution(goals_probabilities)
    except (ValueError, TypeError, OverflowError) as exc:
        result["reason"] = str(exc)
        return result
    if decimal_odds is None:
        result["reason"] = "NO_OBSERVED_DECIMAL_PRICE"
        return result
    if not _number(decimal_odds, 1.01, 100):
        result["reason"] = "INVALID_DECIMAL_PRICE"
        return result
    signed_goals = ({n: p for n, p in distribution.items()} if side == "OVER"
                    else {-n: p for n, p in distribution.items()})
    signed_line = -units / 4 if side == "OVER" else units / 4
    result["nominal_ev_per_unit_claimed_price"] = round(
        expected_value(signed_goals, signed_line, decimal_odds), 8)
    five_grade = {grade: 0.0 for grade in GRADES}
    for goals, p in distribution.items():
        five_grade[_grade(goals, side, units)] += p
    result["five_grade_probabilities_unverified"] = {
        grade: round(five_grade[grade], 8) for grade in GRADES}
    if decimal_odds < DEFAULT_MIN_DECIMAL_ODDS:
        result["reason"] = "ODDS_BELOW_MINIMUM"
        return result
    if conservative_goal_lower_bounds is None:
        result["reason"] = "NO_CONSERVATIVE_TOTAL_LOWER_BOUNDS"
        return result
    try:
        lower = _distribution(conservative_goal_lower_bounds, original=distribution)
    except (ValueError, TypeError, OverflowError) as exc:
        result["reason"] = str(exc)
        return result
    # Simultaneous per-total lower bounds leave all unprotected mass free to
    # suffer a FULL_LOSS; this pessimistic construction is only algebra.
    leftover = max(0.0, 1 - math.fsum(lower.values()))
    lower_ev = math.fsum(p * _profit(n, side, units, decimal_odds)
                         for n, p in lower.items()) - leftover
    result["conservative_ev_lower_bound_if_claims_valid"] = round(lower_ev, 8)
    if lower_ev < DEFAULT_MIN_CONSERVATIVE_EV - 1e-10:
        result["reason"] = "INSUFFICIENT_CONSERVATIVE_TOTAL_EV"
        return result
    if not _number(quote_age_seconds, 0, MAX_QUOTE_AGE_SECONDS):
        result["reason"] = "MISSING_OR_STALE_CLAIMED_QUOTE"
        return result
    result["status"] = "RESEARCH_ONLY"
    result["reason"] = "TOTAL_MATH_ONLY_REQUIRES_EXTERNAL_CERTIFICATION"
    result["research_value_screen_pass"] = True
    return result
