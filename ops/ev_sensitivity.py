"""Compare user-supplied settlement scenarios without claiming model certification.

This module does not infer outcomes or fetch bookmaker prices. The numeric
range is NOT a statistical confidence interval or independently verified edge.
"""
from math import isfinite

SETTLEMENT_OUTCOMES = ("full_win", "half_win", "push", "half_loss", "full_loss")
MAX_SCENARIOS = 12


def _probabilities(raw):
    if not isinstance(raw, dict) or set(raw) != set(SETTLEMENT_OUTCOMES):
        raise ValueError("INVALID_SETTLEMENT_KEYS")
    result = []
    for key in SETTLEMENT_OUTCOMES:
        value = raw[key]
        if type(value) not in (float, int) or not isfinite(value) or not 0 <= value <= 1:
            raise ValueError("INVALID_SETTLEMENT_PROBABILITY")
        result.append(float(value))
    if abs(sum(result) - 1) > 1e-8:
        raise ValueError("SETTLEMENT_NOT_NORMALIZED")
    return result


def analyze_scenarios(scenarios, decimal_odds):
    """Return numerical sensitivity only; never certify an EV or recommend bets.

    Each scenario must name its model and provide complete five-way settlement
    probabilities for the exact quote market, side and line at the caller.
    Two or more supplied models are required before a numeric range is shown.
    There is no implied independence or out-of-sample validation.
    """
    if type(decimal_odds) not in (int, float) or not isfinite(decimal_odds) or not 1 < decimal_odds <= 100:
        raise ValueError("INVALID_ODDS")
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= MAX_SCENARIOS:
        raise ValueError("INVALID_SCENARIO_COUNT")
    ids = set()
    values = []
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise ValueError("INVALID_MODEL_SCENARIO")
        name = scenario.get("model_id")
        if not isinstance(name, str) or not name.strip() or len(name) > 128 or name in ids:
            raise ValueError("DUPLICATE_OR_MISSING_MODEL_ID")
        ids.add(name)
        p = _probabilities(scenario.get("settlement_probabilities"))
        values.append(p[0] * (decimal_odds - 1) +
                      p[1] * (decimal_odds - 1) / 2 -
                      p[3] / 2 - p[4])
    base = {"scenario_count": len(values),
            "positive_ev_verified": False,
            "model_independence_verified": False,
            "sensitivity_is_confidence_interval": False}
    if len(values) < 2:
        return {**base, "ev_sensitivity_status": "INSUFFICIENT_SCENARIOS"}
    low, high = min(values), max(values)
    status = ("ALL_SUPPLIED_SCENARIOS_NUMERICALLY_POSITIVE" if low > 0 else
              "SCENARIO_SIGN_CONFLICT" if high > 0 else
              "NO_POSITIVE_NUMERIC_EDGE_IN_SCENARIOS")
    return {**base, "ev_sensitivity_status": status,
            "scenario_ev_min": round(low, 6),
            "scenario_ev_max": round(high, 6)}
