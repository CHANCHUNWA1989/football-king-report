"""Fail-closed, offline settlement and evidence admission for the Nov-15 research slate.

No network calls, odds access, bet recommendations or certified fixture data.
"""
from decimal import Decimal
from typing import Optional

VALID_STATUS = {"FT_REGULATION"}
OUTCOMES = {"FULL_WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "FULL_LOSS"}


def _result(side: str, line: Decimal, home: int, away: int) -> str:
    if side == "HOME":
        margin = Decimal(home - away) + line
    elif side == "AWAY":
        margin = Decimal(away - home) + line
    elif side == "UNDER":
        margin = line - Decimal(home + away)
    elif side == "OVER":
        margin = Decimal(home + away) - line
    else:
        raise ValueError("invalid selection")
    return "W" if margin > 0 else "L" if margin < 0 else "P"


def settle(selection: str, line: Optional[str], home: int, away: int,
           official_ft: bool = False, independent_ft: bool = False) -> str:
    """Only settle when two source-level regulation-FT attestations are supplied.

    This flag-based helper does NOT authenticate sources. Caller must independently
    validate original evidence, upstream independence and match identity.
    """
    if not (official_ft and independent_ft):
        return "PENDING_EVIDENCE"
    if any(type(v) is not int or v < 0 for v in (home, away)):
        raise ValueError("invalid score")
    if selection == "AWAY_1X2":
        return "FULL_WIN" if away > home else "FULL_LOSS"
    if selection not in {"HOME", "AWAY", "UNDER", "OVER"} or line is None:
        raise ValueError("invalid market or line")
    handicap = Decimal(line)
    if not handicap.is_finite() or handicap * 4 != (handicap * 4).to_integral_value():
        raise ValueError("line must be finite quarter goal")
    if selection in {"UNDER", "OVER"} and handicap < 0:
        raise ValueError("invalid total")
    # Quarter lines split into two half-stakes on adjacent half-goal lines.
    twice = handicap * 2
    if twice == twice.to_integral_value():
        legs = [handicap, handicap]
    else:
        low = (handicap * 2).to_integral_value(rounding="ROUND_FLOOR") / 2
        legs = [low, low + Decimal("0.5")]
    results = [_result(selection, leg, home, away) for leg in legs]
    wins, losses = results.count("W"), results.count("L")
    if wins == 2:
        return "FULL_WIN"
    if losses == 2:
        return "FULL_LOSS"
    if wins == 1 and losses == 0:
        return "HALF_WIN"
    if losses == 1 and wins == 0:
        return "HALF_LOSS"
    if wins == 0 and losses == 0:
        return "PUSH"
    raise ValueError("unexpected mixed settlement")
