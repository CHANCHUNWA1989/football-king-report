"""Offline settlement for full-time 2.5-goal totals; no odds fetching.

This module deliberately supports only the half-goal 2.5 line. Quarter and
whole-goal settlement must be implemented separately before use.
"""


def settle_total_2_5(home_goals, away_goals, side):
    if type(home_goals) is not int or type(away_goals) is not int:
        raise ValueError("INVALID_SCORE")
    if home_goals < 0 or away_goals < 0:
        raise ValueError("INVALID_SCORE")
    if side not in ("Over", "Under"):
        raise ValueError("INVALID_SIDE")
    total = home_goals + away_goals
    return "WIN" if (total > 2.5) == (side == "Over") else "LOSS"


def flat_stake_profit(result, decimal_odds):
    if result not in ("WIN", "LOSS"):
        raise ValueError("INVALID_SETTLEMENT")
    if type(decimal_odds) not in (int, float) or not 1.01 <= decimal_odds <= 500:
        raise ValueError("INVALID_ODDS")
    return round(decimal_odds - 1 if result == "WIN" else -1, 6)
