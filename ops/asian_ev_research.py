"""Research-only Asian settlement expected value utilities.

Returns net profit per unit staked. Probabilities must come from an independently
validated distribution; positive numerical EV is NOT evidence of calibration.
"""
from math import isfinite

def _settle_quarters(margin, units):
    adjusted = 4 * margin + units
    if adjusted > 0:
        return 1.0
    if adjusted < 0:
        return -1.0
    return 0.0


def _quarter_units(line):
    # Keep the existing finite-scaled-line safety boundary. Integer arithmetic
    # must not silently admit values the old numeric guard rejected.
    try:
        finite_scaled = isfinite(line * 4)
    except OverflowError:
        finite_scaled = False
    if not finite_scaled:
        raise ValueError("LINE_MUST_BE_QUARTER")
    if type(line) is int:
        return 4 * line
    if not isfinite(line):
        raise ValueError("LINE_MUST_BE_QUARTER")
    numerator, denominator = line.as_integer_ratio()
    units, remainder = divmod(4 * numerator, denominator)
    if remainder:
        raise ValueError("LINE_MUST_BE_QUARTER")
    return units

def asian_net(margin, line, decimal_odds):
    """Net return per 1 unit stake, given integer score margin and signed handicap.

    For totals, margin = actual total goals and line = -selected threshold.
    For team handicap, margin = selected team's goals minus opponent goals.
    """
    if type(margin) is not int or type(line) not in (int, float):
        raise ValueError("INVALID_MARGIN_OR_LINE")
    q = _quarter_units(line)
    if type(decimal_odds) not in (int, float) or not isfinite(decimal_odds) or decimal_odds <= 1:
        raise ValueError("INVALID_DECIMAL_ODDS")
    if q % 2:
        outcome = (_settle_quarters(margin, q - 1) + _settle_quarters(margin, q + 1)) / 2
    else:
        outcome = _settle_quarters(margin, q)
    return outcome * (decimal_odds - 1) if outcome > 0 else outcome

def expected_value(outcome_probabilities, line, decimal_odds):
    """Map integer score margins/totals to probabilities; return research EV.

    This function does not certify source freshness, probability calibration,
    independence, executable price, or permission to issue a recommendation.
    """
    if not isinstance(outcome_probabilities, dict) or not outcome_probabilities:
        raise ValueError("MISSING_DISTRIBUTION")
    if any(type(k) is not int or type(p) not in (int, float)
           or not isfinite(p) or p < 0 for k, p in outcome_probabilities.items()):
        raise ValueError("INVALID_DISTRIBUTION")
    if abs(sum(outcome_probabilities.values()) - 1) > 1e-8:
        raise ValueError("DISTRIBUTION_NOT_NORMALIZED")
    return sum(p * asian_net(k, line, decimal_odds)
               for k, p in outcome_probabilities.items())

PRODUCTION_RECOMMENDATIONS = "DISABLED"
