"""Non-executable point-in-time fair-price diagnostics for 1X2 and nearby Asian lines.

This module consumes frozen model and no-vig market 1X2 probability vectors.
Neither is a verified executable bookmaker quote or a calibrated betting edge.
It never alters sealed A/B/C probabilities, retroactively uses results or
promotes recommendations. A 1X2 vector cannot price goal totals or deep spreads.
"""
import math

OUTCOMES = ("FULL_WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "FULL_LOSS")
SUPPORTED_LINES = (-0.5, -0.25, 0.0, 0.25, 0.5)


def _probabilities(values):
    if (not isinstance(values, (list, tuple)) or len(values) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v)
                   or not 0 <= v <= 1 for v in values)
            or abs(sum(values) - 1.0) > 0.002):
        raise ValueError("INVALID_1X2_PROBABILITIES")
    total = sum(values)
    if total <= 0:
        raise ValueError("INVALID_1X2_PROBABILITIES")
    return [v / total for v in values]


def _decimal_odds(price):
    if type(price) not in (int, float) or not math.isfinite(price) or not 1.01 <= price <= 100:
        raise ValueError("INVALID_DECIMAL_ODDS")
    return float(price)


def _grades(weights):
    if (not isinstance(weights, dict) or set(weights) != set(OUTCOMES)
            or any(type(weights[k]) not in (float, int)
                   or not math.isfinite(weights[k]) or weights[k] < 0
                   for k in OUTCOMES)
            or abs(sum(weights.values()) - 1) > 0.002):
        raise ValueError("INVALID_SETTLEMENT_PROBABILITIES")
    total = sum(weights.values())
    return {k: weights[k] / total for k in OUTCOMES}


def neutral_decimal_price(grades):
    """Full/half-win/push/half-loss/full-loss stake-weighted break-even price."""
    g = _grades(grades)
    win = g["FULL_WIN"] + 0.5 * g["HALF_WIN"]
    loss = g["FULL_LOSS"] + 0.5 * g["HALF_LOSS"]
    return 1 + loss / win if win else None


def hypothetical_profit(grades, decimal_odds):
    """Pure algebra, never proof of positive EV or an executable bookmaker quote."""
    price = _decimal_odds(decimal_odds)
    g = _grades(grades)
    return ((price - 1) * (g["FULL_WIN"] + g["HALF_WIN"] / 2)
            - g["FULL_LOSS"] - g["HALF_LOSS"] / 2)


def home_handicap_distribution(probabilities, line):
    """Grade only ±0.5 and quarter/zero lines derivable from three 1X2 outcomes.

    0.75, 1.0 and deeper lines need a score-difference distribution; totals
    need a goals distribution. Neither can be inferred from 1X2 alone.
    """
    p_home, p_draw, p_away = _probabilities(probabilities)
    if type(line) not in (int, float) or line not in SUPPORTED_LINES:
        raise ValueError("UNSUPPORTED_HANDICAP_WITHOUT_GOAL_DISTRIBUTION")
    out = {k: 0.0 for k in OUTCOMES}
    out["FULL_WIN"] = p_home
    out["FULL_LOSS"] = p_away
    if line == -0.5:
        out["FULL_LOSS"] += p_draw
    elif line == -0.25:
        out["HALF_LOSS"] = p_draw
    elif line == 0.0:
        out["PUSH"] = p_draw
    elif line == 0.25:
        out["HALF_WIN"] = p_draw
    else:
        out["FULL_WIN"] += p_draw
    return out


def audit_1x2(model, market):
    """Snapshot diagnostics attached ONLY after an earlier-market 1X2 pair."""
    a, m = _probabilities(model), _probabilities(market)

    def fair(p):
        return round(1 / p, 5) if p else None

    def handicap(p, line):
        price = neutral_decimal_price(home_handicap_distribution(p, line))
        return round(price, 5) if price is not None else None

    return {
        "status": "RESEARCH_ONLY",
        "market_reference_fair_1x2_not_quotes": [fair(p) for p in m],
        "uncalibrated_model_fair_1x2_not_quotes": [fair(p) for p in a],
        "max_absolute_model_market_gap": round(max(abs(x-y) for x, y in zip(a, m)), 7),
        "market_reference_home_plus_0_25_fair_not_quote": handicap(m, 0.25),
        "market_reference_home_plus_0_5_fair_not_quote": handicap(m, 0.5),
        "market_reference_home_minus_0_25_fair_not_quote": handicap(m, -0.25),
        "market_reference_home_zero_fair_not_quote": handicap(m, 0),
        "market_probability_is_de_vigged_reference_not_licensed_execution": True,
        "independent_calibration_verified": False,
        "official_lineup_incorporation_verified": False,
        "quote_executable_verified": False,
        "betting_positive_ev_verified": False,
        "recommendation": None,
        "production_recommendations": "DISABLED",
    }
