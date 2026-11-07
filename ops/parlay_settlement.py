"""Research-only deterministic parlay settlement; no market data or betting actions."""
from decimal import Decimal, InvalidOperation
from ops.asian_settlement import settle

PRODUCTION_RECOMMENDATIONS = "DISABLED"
POSITIVE_EV_VERIFIED = False

def _money(value):
    if isinstance(value, bool):
        raise ValueError("invalid numeric input")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid numeric input") from exc
    if not result.is_finite():
        raise ValueError("nonfinite numeric input")
    return result

def parlay_return(stake, legs):
    """Return (gross payout, net profit) for an all-legs accumulator.

    Each leg specifies market, side, line, home_goals, away_goals and odds.
    Quarter-line legs use stake-weighted gross settlement factors.
    Provider-specific currency rounding is intentionally not applied.
    """
    amount = _money(stake)
    if amount <= 0:
        raise ValueError("stake must be positive")
    if not isinstance(legs, (list, tuple)) or not legs:
        raise ValueError("legs must be a nonempty list or tuple")
    factor = Decimal(1)
    for leg in legs:
        if not isinstance(leg, dict):
            raise ValueError("each leg must be a mapping")
        try:
            net = settle(leg["market"], leg["side"], leg["line"],
                         leg["home_goals"], leg["away_goals"], leg["odds"])
        except KeyError as exc:
            raise ValueError("leg missing required field") from exc
        factor *= (Decimal(1) + net)
    gross = amount * factor
    return gross, gross - amount
