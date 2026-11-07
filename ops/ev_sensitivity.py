"""Compare user-supplied settlement scenarios without claiming model certification.

This module does not infer outcomes or fetch bookmaker prices. The numeric
range is NOT a statistical confidence interval or independently verified edge.
"""
from math import isfinite
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

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



def _utc(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_SCENARIO_TIME")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_SCENARIO_TIME") from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("NAIVE_SCENARIO_TIME")
    return stamp.astimezone(timezone.utc)


def _quarter_line(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("INVALID_SCENARIO_LINE")
    try:
        line = Decimal(str(value))
        if not line.is_finite() or line * 4 != (line * 4).to_integral_value():
            raise ValueError("INVALID_SCENARIO_LINE")
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise ValueError("INVALID_SCENARIO_LINE") from exc
    return line


def _verify_scenario_identity(scenario, quote, observed, kickoff, line, cutoff):
    for key in ("fixture_id", "market", "selection"):
        if (not isinstance(scenario.get(key), str)
                or not isinstance(quote.get(key), str)
                or not quote[key].strip()
                or scenario[key] != quote[key]):
            raise ValueError("SCENARIO_QUOTE_IDENTITY_MISMATCH")
    if _quarter_line(scenario.get("line")) != line:
        raise ValueError("SCENARIO_LINE_MISMATCH")
    if _utc(scenario.get("kickoff_utc")) != kickoff:
        raise ValueError("SCENARIO_KICKOFF_MISMATCH")
    forecast = _utc(scenario.get("forecast_created_utc"))
    if (_utc(scenario.get("information_cutoff_utc")) != cutoff
            or cutoff > forecast):
        raise ValueError("SCENARIO_INFORMATION_CUTOFF_MISMATCH")
    # A scenario created at/after the bookmaker update could see later
    # information than the quoted evidence; do not use it in this comparison.
    if not forecast < observed:
        raise ValueError("SCENARIO_FORECAST_NOT_BEFORE_QUOTE")

def analyze_scenarios(scenarios, decimal_odds, *, quote):
    """Return numerical sensitivity only; never certify an EV or recommend bets.

    Each scenario must name its model and provide complete five-way settlement
    probabilities, exact fixture/market/selection/quarter-line and kickoff.
    Information cutoffs must equal the reference quote's information_cutoff_utc
    and be no later than each forecast creation UTC. Each forecast creation
    UTC must strictly predate the source quote update.
    Two or more supplied models are required before a numeric range is shown.
    There is no implied independence or out-of-sample validation.
    """
    if type(decimal_odds) not in (int, float) or not isfinite(decimal_odds) or not 1 < decimal_odds <= 100:
        raise ValueError("INVALID_ODDS")
    if not isinstance(quote, dict):
        raise ValueError("INVALID_REFERENCE_QUOTE")
    observed, kickoff = _utc(quote.get("observed_utc")), _utc(quote.get("kickoff_utc"))
    cutoff = _utc(quote.get("information_cutoff_utc"))
    line = _quarter_line(quote.get("line"))
    if observed >= kickoff:
        raise ValueError("INVALID_REFERENCE_CHRONOLOGY")
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
        _verify_scenario_identity(scenario, quote, observed, kickoff, line, cutoff)
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
