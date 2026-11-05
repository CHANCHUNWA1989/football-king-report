"""Research-only Asian handicap/totals settlement. No quotes, EV or betting actions."""
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

def _decimal(value):
    if isinstance(value, bool):
        raise ValueError("boolean is not a valid number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid numeric input") from exc
    if not result.is_finite():
        raise ValueError("nonfinite numeric input")
    return result

def _legs(line):
    line = _decimal(line)
    quarters = line * 4
    if quarters != quarters.to_integral_value():
        raise ValueError("line must be in quarter-goal increments")
    lower = (line * 2).to_integral_value(rounding=ROUND_FLOOR) / 2
    if line == lower:
        return (line,)
    return (lower, lower + Decimal("0.5"))

def _unit_result(adjusted):
    return Decimal(1) if adjusted > 0 else Decimal(-1) if adjusted < 0 else Decimal(0)

def settle(market, side, line, home_goals, away_goals, odds):
    """Return net profit per 1 unit stake, including split quarter lines.

    market: 'handicap' or 'total'; side: home/away or over/under.
    Positive result is profit; -1 is a lost stake; 0 is a push.
    """
    hg, ag, price = _decimal(home_goals), _decimal(away_goals), _decimal(odds)
    if hg < 0 or ag < 0 or hg != hg.to_integral_value() or ag != ag.to_integral_value():
        raise ValueError("scores must be nonnegative integers")
    if price <= 1:
        raise ValueError("decimal odds must exceed 1")
    if market == "handicap" and side in ("home", "away"):
        margin = hg - ag if side == "home" else ag - hg
        grade = lambda part: _unit_result(margin + part)
    elif market == "total" and side in ("over", "under"):
        goals = hg + ag
        grade = lambda part: _unit_result(goals - part if side == "over" else part - goals)
    else:
        raise ValueError("invalid market/side")
    parts = _legs(line)
    returns = [(price - 1 if grade(part) > 0 else Decimal(-1) if grade(part) < 0 else Decimal(0)) for part in parts]
    return sum(returns) / Decimal(len(returns))

def expected_profit(market, side, line, odds, score_probabilities):
    """Research-only expected net return, never verified positive EV."""
    probabilities = [(_decimal(p), settle(market, side, line, h, a, odds))
                     for (h, a), p in score_probabilities.items()]
    if any(p < 0 for p, _ in probabilities) or abs(sum(p for p, _ in probabilities) - 1) > Decimal("0.000001"):
        raise ValueError("score probabilities must be nonnegative and sum to one")
    return sum(p * result for p, result in probabilities)

PRODUCTION_RECOMMENDATIONS = "DISABLED"
POSITIVE_EV_VERIFIED = False
