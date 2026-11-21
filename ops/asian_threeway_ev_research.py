"""Fail-closed research screen for Asian quarter-handicap EV from 1X2 inputs.

Only lines from -0.5 to +0.5 are covered: for those lines the
win/draw/loss result fully determines the net payout. Larger handicaps
require an entire score-margin distribution, NOT only 1X2 probabilities.

All input probabilities, prices, quote times and lower bounds are CLAIMS.
Neither a mathematically positive EV nor a retrospective winner permits
production picks, staking, or entry in the certified settlement ledger.
"""
import math

from asian_ev_research import asian_net, expected_value
from asian_handicap_research import quarter_units
from value_ev_policy import (
    DEFAULT_MIN_DECIMAL_ODDS, DEFAULT_MIN_CONSERVATIVE_EV,
    MAX_QUOTE_AGE_SECONDS,
)

SCHEMA = "football-king-asian-threeway-ev-research-v1"


def _number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def _vector(value):
    if (not isinstance(value, (list, tuple)) or len(value) != 3
            or any(not _number(p, 0, 1) for p in value)
            or abs(math.fsum(value) - 1) > 1e-8):
        raise ValueError("INVALID_THREEWAY_PROBABILITIES")
    return value


def _lower_vector(value, original):
    if (not isinstance(value, (list, tuple)) or len(value) != 3
            or any(not _number(p, 0, original[i]) for i, p in enumerate(value))
            or math.fsum(value) > 1 + 1e-10):
        raise ValueError("INVALID_CONSERVATIVE_LOWER_BOUNDS")
    return value


def _selected_margin_distribution(p, side):
    # Scores are represented only by the result class; never feed this
    # distribution into an Asian line of 0.75, 1.0, etc.
    win = p[0] if side == "HOME" else p[2]
    draw = p[1]
    loss = p[2] if side == "HOME" else p[0]
    return {-1: loss, 0: draw, 1: win}


def assess(p_home_draw_away, *, side, handicap, decimal_odds=None,
           lower_bounds_home_draw_away=None, quote_age_seconds=None):
    """Screen a stated pre-match research scenario, never authenticate it.

    A simultaneous conservative lower bound on selected-team win and draw
    implies the worst-case remaining mass is a selected-team loss. This
    gives a mathematical lower EV bound, not a *calibrated* confidence bound.
    """
    out = {
        "schema": SCHEMA,
        "status": "HOLD",
        "reason": "UNKNOWN",
        "asian_line_is_research_only": True,
        "threeway_inputs_independently_authenticated": False,
        "price_executable_authenticated": False,
        "calibration_lower_bounds_independently_authenticated": False,
        "quote_timestamp_independently_authenticated": False,
        "positive_expected_value_verified": False,
        "can_enter_formal_settlement_ledger": False,
        "formal_bet_count": 0,
        "recommended_stake": None,
        "production_recommendations": "DISABLED",
        "research_value_screen_pass": False,
        "nominal_ev_per_unit_claimed_price": None,
        "conservative_ev_lower_bound_if_claims_valid": None,
        "break_even_win_probability_conditional_on_claimed_draw": None,
        "minimum_decimal_odds": DEFAULT_MIN_DECIMAL_ODDS,
        "minimum_conservative_ev": DEFAULT_MIN_CONSERVATIVE_EV,
        "max_quote_age_seconds": MAX_QUOTE_AGE_SECONDS,
    }
    try:
        p = _vector(p_home_draw_away)
        if side not in ("HOME", "AWAY"):
            raise ValueError("INVALID_SELECTED_TEAM_SIDE")
        if type(handicap) not in (int, float):
            raise ValueError("INVALID_ASIAN_HANDICAP")
        units = quarter_units(handicap)
    except (TypeError, ValueError) as exc:
        out["reason"] = str(exc)
        return out

    if abs(units) > 2:
        out["reason"] = "NEEDS_FULL_SCORE_MARGIN_DISTRIBUTION"
        return out
    if decimal_odds is None:
        out["reason"] = "NO_OBSERVED_DECIMAL_PRICE"
        return out
    if not _number(decimal_odds, 1.01, 100):
        out["reason"] = "INVALID_DECIMAL_PRICE"
        return out

    chosen = _selected_margin_distribution(p, side)
    nominal_ev = expected_value(chosen, handicap, decimal_odds)
    # Exact three-way Asian payoffs, including half-loss, half-win, push.
    out["nominal_ev_per_unit_claimed_price"] = round(nominal_ev, 8)
    win_return = asian_net(1, handicap, decimal_odds)
    draw_return = asian_net(0, handicap, decimal_odds)
    lose_return = asian_net(-1, handicap, decimal_odds)
    win_threshold = (-lose_return - chosen[0] * (draw_return - lose_return)) / (
        win_return - lose_return)
    out["break_even_win_probability_conditional_on_claimed_draw"] = round(
        win_threshold, 8)

    if decimal_odds < DEFAULT_MIN_DECIMAL_ODDS:
        out["reason"] = "ODDS_BELOW_MINIMUM"
        return out
    if lower_bounds_home_draw_away is None:
        out["reason"] = "NO_CONSERVATIVE_PROBABILITY_BOUNDS"
        return out
    try:
        lower = _lower_vector(lower_bounds_home_draw_away, p)
    except ValueError as exc:
        out["reason"] = str(exc)
        return out

    lower_chosen = _selected_margin_distribution(lower, side)
    # Put all probability mass not protected by stated lower bounds on a
    # loss, the worst payoff for a selected team on these bounded lines.
    worst = {
        -1: 1 - lower_chosen[0] - lower_chosen[1],
        0: lower_chosen[0],
        1: lower_chosen[1],
    }
    conservative_ev = expected_value(worst, handicap, decimal_odds)
    out["conservative_ev_lower_bound_if_claims_valid"] = round(conservative_ev, 8)
    if conservative_ev < DEFAULT_MIN_CONSERVATIVE_EV - 1e-10:
        out["reason"] = "INSUFFICIENT_CONSERVATIVE_EV"
        return out
    if not _number(quote_age_seconds, 0, MAX_QUOTE_AGE_SECONDS):
        out["reason"] = "MISSING_OR_STALE_CLAIMED_QUOTE"
        return out

    out["status"] = "RESEARCH_ONLY"
    out["reason"] = "MATH_SCREEN_ONLY_REQUIRES_EXTERNAL_CERTIFICATION"
    out["research_value_screen_pass"] = True
    return out
