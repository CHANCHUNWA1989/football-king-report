"""Research-only Asian settlement expected value utilities.

Returns net profit per unit staked. Probabilities must come from an independently
validated distribution; positive numerical EV is NOT evidence of calibration.
"""
from math import isfinite

def _settle_integer(margin, line):
    adjusted = margin + line
    if adjusted > 1e-9:
        return 1.0
    if adjusted < -1e-9:
        return -1.0
    return 0.0

def asian_net(margin, line, decimal_odds):
    """Net return per 1 unit stake, given integer score margin and signed handicap.

    For totals, margin = actual total goals and line = -selected threshold.
    For team handicap, margin = selected team's goals minus opponent goals.
    """
    if type(margin) is not int or type(line) not in (int, float):
        raise ValueError("INVALID_MARGIN_OR_LINE")
    if not isfinite(line) or abs(line * 4 - round(line * 4)) > 1e-8:
        raise ValueError("LINE_MUST_BE_QUARTER")
    if type(decimal_odds) not in (int, float) or not isfinite(decimal_odds) or decimal_odds <= 1:
        raise ValueError("INVALID_DECIMAL_ODDS")
    q = round(line * 4)
    if q % 2:
        lower = (q - 1) / 4
        upper = (q + 1) / 4
        outcome = (_settle_integer(margin, lower) + _settle_integer(margin, upper)) / 2
    else:
        outcome = _settle_integer(margin, line)
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
