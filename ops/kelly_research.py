"""Offline, hypothetical Kelly diagnostics for Asian handicap and totals.

This module is a research-only sidecar: it does not read bankrolls, generate
bet sizes, authenticate bookmaker prices, calibrate model probabilities,
or change production readiness. The caller MUST NOT interpret an algebraic
Kelly solution as a betting recommendation or a certified positive edge.

Margin convention follows asian_ev_research.asian_net:
* selected team handicap: selected goals minus opponent goals, signed line;
* OVER totals: actual goals with negative threshold;
* UNDER totals: negative actual goals with positive threshold.
"""
from math import isfinite, log1p

from ops.asian_ev_research import asian_net, expected_value

PRODUCTION_RECOMMENDATIONS = "DISABLED"
MAX_ODDS = 100.0
MAX_ITERATIONS = 96
# Keep the logarithm well-defined for a possible full loss (-1 per unit).
UPPER_FRACTION = 1.0 - 1e-12


def _validated_returns(probabilities, line, decimal_odds):
    """Return EV and finite probability-weighted net-return outcomes."""
    if (type(decimal_odds) not in (int, float)
            or not isfinite(decimal_odds)
            or not 1.0 < decimal_odds <= MAX_ODDS):
        raise ValueError("INVALID_DECIMAL_ODDS")
    # Existing engine validates a normalized integer-margin distribution,
    # quarter-point line, finite prices, booleans and settlement semantics.
    ev = expected_value(probabilities, line, decimal_odds)
    returns = tuple(
        (float(probability), asian_net(margin, line, decimal_odds))
        for margin, probability in probabilities.items()
        if probability > 0.0
    )
    if not isfinite(ev) or not returns:
        raise ValueError("INVALID_EXPECTED_VALUE")
    return ev, returns


def theoretical_kelly(probabilities, line, decimal_odds):
    """Maximize sum(p * log(1 + f * net_return)) for 0 <= f < 1.

    This is a mathematical hypothetical, NOT an independently validated
    probability, executable quote, real Kelly stake or release approval.
    An asserted positive edge with no possible loss is rejected instead
    of outputting a misleading full-bankroll fraction.
    """
    ev, returns = _validated_returns(probabilities, line, decimal_odds)
    if ev <= 0.0:
        fraction = 0.0
    else:
        if not any(prob > 0.0 and result < 0.0 for prob, result in returns):
            raise ValueError("NO_DOWNSIDE_IN_DISTRIBUTION")
        if not any(prob > 0.0 and result > 0.0 for prob, result in returns):
            raise ValueError("NO_UPSIDE_IN_DISTRIBUTION")

        def derivative(fraction):
            return sum(prob * result / (1.0 + fraction * result)
                       for prob, result in returns)

        low, high = 0.0, UPPER_FRACTION
        if derivative(high) > 0.0:
            fraction = high
        else:
            for _ in range(MAX_ITERATIONS):
                mid = (low + high) / 2.0
                if derivative(mid) > 0.0:
                    low = mid
                else:
                    high = mid
            fraction = (low + high) / 2.0

    log_growth = sum(prob * log1p(fraction * result)
                     for prob, result in returns)
    return {
        "status": "HYPOTHETICAL_ONLY",
        "research_ev_per_unit": ev,
        "full_kelly_fraction": fraction,
        "half_kelly_fraction": fraction / 2.0,
        "quarter_kelly_fraction": fraction / 4.0,
        "hypothetical_log_growth": log_growth,
        "independent_probability_calibration_verified": False,
        "executable_quote_verified": False,
        "bet_eligible": False,
        "suggested_stake": None,
        "production_recommendations": PRODUCTION_RECOMMENDATIONS,
    }


def assess(probabilities=None, line=None, decimal_odds=None, *, hypothetical=False):
    """Fail closed for real cases; opt-in hypothetical arithmetic only.

    Do not infer that numerical input values are actual sealed predictions
    or a live price. No set of caller-provided flags can unlock betting.
    """
    held = {
        "status": "HOLD",
        "reason": "NO_INDEPENDENTLY_CALIBRATED_MODEL_OR_EXECUTABLE_QUOTE",
        "research_ev_per_unit": None,
        "full_kelly_fraction": None,
        "half_kelly_fraction": None,
        "quarter_kelly_fraction": None,
        "independent_probability_calibration_verified": False,
        "executable_quote_verified": False,
        "bet_eligible": False,
        "suggested_stake": None,
        "production_recommendations": PRODUCTION_RECOMMENDATIONS,
    }
    if hypothetical is not True:
        return held
    return theoretical_kelly(probabilities, line, decimal_odds)
