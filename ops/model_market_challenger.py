"""Frozen, pre-kickoff, market-anchored 1X2 challenger C (research only).

C is 25% original Poisson shadow + 75% contemporaneous *earlier*
de-vigged market consensus. This weight is a fixed prospective policy choice,
NOT estimated from the seven previously settled games. It makes no claim
of beating the market, calibration, executable odds, or betting value.
An evaluation must compare C, A and the same market on exactly the same
future settled fixtures. No model fitting and no outcome inputs are used.
"""
import math

MODEL = "market-anchored-fixed-25pct-model-75pct-consensus-v1"
MODEL_WEIGHT = 0.25
MARKET_WEIGHT = 0.75


def valid_vector(values):
    return (
        isinstance(values, list) and len(values) == 3
        and all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1
                for v in values)
        and abs(sum(values) - 1) <= 0.002
    )


def candidate(model, market):
    """Construct only from paired, validated, pre-prediction 1X2 vectors."""
    if not valid_vector(model) or not valid_vector(market):
        raise ValueError("INVALID_CHALLENGER_VECTOR")
    # Normalize input before blending to avoid odds-source rounding drifts.
    a = [v / sum(model) for v in model]
    b = [v / sum(market) for v in market]
    combined = [MODEL_WEIGHT * a[i] + MARKET_WEIGHT * b[i] for i in range(3)]
    combined = [v / sum(combined) for v in combined]
    return [round(v, 7) for v in combined]


def matches_sealed(model, market, sealed, sealed_name):
    """Do not accept a later reconstructed or tampered candidate as evidence."""
    if sealed_name != MODEL or not valid_vector(sealed):
        return False
    try:
        expected = candidate(model, market)
    except (ValueError, TypeError):
        return False
    return all(abs(left - right) <= 0.000001 for left, right in zip(sealed, expected))
