"""User-specific, fail-closed EV recommendation gate.

This module never estimates probabilities or fetches prices. A caller must supply
independently validated inputs. Research candidates are not betting advice.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Optional

MIN_ODDS = 1.80
MIN_EV = 0.0
MAX_QUOTE_AGE_SECONDS = 1200

@dataclass(frozen=True)
class EVDecision:
    status: str
    reason: str
    ev: Optional[float] = None
    fair_odds: Optional[float] = None

def evaluate_binary_market(*, odds: float, win_probability: float,
                           source: str, quote_at: datetime,
                           kickoff_at: datetime, model_calibrated: bool,
                           model_validated: bool, identity_verified: bool,
                           now: Optional[datetime] = None) -> EVDecision:
    """For binary full-win/full-loss bets only; not quarter Asian lines.

    Return HOLD for missing, invalid, unverified or stale inputs.
    """
    hold = lambda reason: EVDecision("HOLD", reason)
    if not isinstance(odds, (float, int)) or not isfinite(odds) or odds < MIN_ODDS:
        return hold("ODDS_BELOW_MIN_OR_INVALID")
    if not isinstance(win_probability, (float, int)) or not isfinite(win_probability) or not 0 < win_probability < 1:
        return hold("PROBABILITY_INVALID")
    if not source or not source.strip():
        return hold("QUOTE_SOURCE_MISSING")
    if not model_calibrated or not model_validated:
        return hold("MODEL_NOT_INDEPENDENTLY_VALIDATED")
    if not identity_verified:
        return hold("EVENT_MARKET_IDENTITY_UNVERIFIED")
    now = now or datetime.now(timezone.utc)
    dates = (quote_at, kickoff_at, now)
    if any(not isinstance(d, datetime) or d.tzinfo is None or d.utcoffset() is None for d in dates):
        return hold("TIMESTAMP_INVALID")
    age = (now - quote_at).total_seconds()
    if age < 0 or age > MAX_QUOTE_AGE_SECONDS or now >= kickoff_at or quote_at >= kickoff_at:
        return hold("QUOTE_STALE_OR_EVENT_STARTED")
    ev = odds * win_probability - 1.0
    fair = 1.0 / win_probability
    if ev <= MIN_EV:
        return EVDecision("HOLD", "NON_POSITIVE_EV", ev, fair)
    return EVDecision("ELIGIBLE_RESEARCH", "POSITIVE_EV_VALIDATED_INPUTS", ev, fair)
