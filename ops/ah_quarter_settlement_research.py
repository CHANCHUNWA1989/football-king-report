"""Research-only Asian handicap settlement for decimal odds and unit stake.

Uses exact quarter-goal arithmetic (Decimal). Does not obtain prices, validate
bookmaker quotes, compute EV, or authorize any betting recommendation.
"""
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

GRADES = ("FULL_WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "FULL_LOSS")


def _decimal(value, label):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("INVALID_" + label)
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("INVALID_" + label) from exc
    if not number.is_finite():
        raise ValueError("INVALID_" + label)
    return number


def settle(home_goals, away_goals, selection, handicap, decimal_odds, stake="1"):
    """Return net P/L and grade; handicap is from selected team's perspective."""
    if type(home_goals) is not int or type(away_goals) is not int or not (0 <= home_goals <= 100 and 0 <= away_goals <= 100):
        raise ValueError("INVALID_SCORE")
    if selection not in ("home", "away"):
        raise ValueError("INVALID_SELECTION")
    h = _decimal(handicap, "HANDICAP")
    if h * 4 != (h * 4).to_integral_value():
        raise ValueError("INVALID_HANDICAP")
    odds = _decimal(decimal_odds, "ODDS")
    amount = _decimal(stake, "STAKE")
    if odds <= 1 or amount <= 0:
        raise ValueError("INVALID_PRICE_OR_STAKE")
    margin = home_goals - away_goals if selection == "home" else away_goals - home_goals
    # Quarter-lines split into two adjacent half-lines; integer and half-lines
    # settle as one line duplicated. Both legs carry half the original stake.
    low = (h * 2).to_integral_value(rounding=ROUND_FLOOR) / Decimal(2)
    high = low if h == low else low + Decimal("0.5")
    outcomes = []
    profit = Decimal(0)
    for line in (low, high):
        adjusted = Decimal(margin) + line
        result = "WIN" if adjusted > 0 else "LOSS" if adjusted < 0 else "PUSH"
        outcomes.append(result)
        if result == "WIN":
            profit += amount / 2 * (odds - 1)
        elif result == "LOSS":
            profit -= amount / 2
    grade = {
        ("WIN", "WIN"): "FULL_WIN",
        ("WIN", "PUSH"): "HALF_WIN",
        ("PUSH", "WIN"): "HALF_WIN",
        ("PUSH", "PUSH"): "PUSH",
        ("LOSS", "PUSH"): "HALF_LOSS",
        ("PUSH", "LOSS"): "HALF_LOSS",
        ("LOSS", "LOSS"): "FULL_LOSS",
    }.get(tuple(outcomes))
    if grade is None:
        raise AssertionError("UNEXPECTED_SPLIT_OUTCOME")
    return {"grade": grade, "net_profit": str(profit), "stake": str(amount),
            "legs": outcomes, "status": "RESEARCH_ONLY",
            "production_recommendations": "DISABLED", "positive_ev_verified": False}
