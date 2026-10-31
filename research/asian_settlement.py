"""Deterministic research settlement, independent of price and EV certification."""
from dataclasses import dataclass
from math import floor, isfinite

@dataclass(frozen=True)
class Settlement:
    status: str
    profit_units: float | None

def settle_asian(*, market, selection, line, home_goals, away_goals, final=False):
    """Quarter lines split equally across adjacent half-step lines; profit at even odds."""
    if not final:
        return Settlement("HOLD", None)
    if any(type(g) is not int or g < 0 for g in (home_goals, away_goals)):
        raise ValueError("Invalid final score")
    if type(line) not in (int, float) or not isfinite(line) or round(line * 4) != line * 4:
        raise ValueError("Line must be a quarter-goal increment")
    if market == "totals" and selection in ("over", "under"):
        margin = (home_goals + away_goals - line) * (1 if selection == "over" else -1)
    elif market == "asian_handicap" and selection in ("home", "away"):
        margin = ((home_goals - away_goals) if selection == "home" else (away_goals - home_goals)) + line
    else:
        raise ValueError("Unsupported market")
    # A quarter line has one half-stake on each neighbouring half-goal line.
    if abs(line * 2 - round(line * 2)) > 1e-9:
        lower = floor(line * 2) / 2
        upper = lower + 0.5
        if market == "totals":
            vals = [((home_goals + away_goals - x) * (1 if selection == "over" else -1)) for x in (lower, upper)]
        else:
            goal_diff = home_goals - away_goals if selection == "home" else away_goals - home_goals
            vals = [goal_diff + x for x in (lower, upper)]
        profit = sum((1 if v > 0 else -1 if v < 0 else 0) / 2 for v in vals)
    else:
        profit = 1 if margin > 0 else -1 if margin < 0 else 0
    statuses = {1:"FULL_WIN", 0.5:"HALF_WIN", 0:"PUSH", -0.5:"HALF_LOSS", -1:"FULL_LOSS"}
    return Settlement(statuses[profit], profit)
