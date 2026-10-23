"""Conditional EV arithmetic for binary full-win/full-loss research inputs.

Caller-supplied model and identity flags are declarations checked for strict
Boolean shape only. This helper does not authenticate a quote, fixture, model,
calibration or executable price, and cannot grant recommendation eligibility.
Positive arithmetic remains UNVERIFIED_RESEARCH. No admission verifier or
production recommendation consumer is implemented here.
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


def _finite_number(value):
    # bool is a subclass of int; caller-defined numeric subclasses can execute
    # conversion methods. Only ordinary finite JSON-style numbers are accepted.
    if type(value) not in (float, int):
        return None
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _utc_datetime(value):
    try:
        if (not isinstance(value, datetime) or value.tzinfo is None
                or value.utcoffset() is None):
            return None
        return value.astimezone(timezone.utc)
    except Exception:
        # Invalid caller-supplied tzinfo implementations must result in HOLD,
        # without copying exception text or substituting a different clock.
        return None


def evaluate_binary_market(*, odds: float, win_probability: float,
                           source: str, quote_at: datetime,
                           kickoff_at: datetime, model_calibrated: bool,
                           model_validated: bool, identity_verified: bool,
                           now: Optional[datetime] = None) -> EVDecision:
    """Compute conditional binary EV; this does not support quarter Asian lines.

    Invalid, stale or non-positive arithmetic returns HOLD. Exact True flags do
    not establish independent validation. A positive result is unverified
    arithmetic and must not be used as an admission or production eligibility
    decision.
    """
    hold = lambda reason: EVDecision("HOLD", reason)
    odds_value = _finite_number(odds)
    if odds_value is None or odds_value < MIN_ODDS:
        return hold("ODDS_BELOW_MIN_OR_INVALID")
    probability = _finite_number(win_probability)
    if probability is None or not 0 < probability < 1:
        return hold("PROBABILITY_INVALID")
    if type(source) is not str or not source.strip():
        return hold("QUOTE_SOURCE_MISSING")
    if model_calibrated is not True or model_validated is not True:
        return hold("MODEL_NOT_INDEPENDENTLY_VALIDATED")
    if identity_verified is not True:
        return hold("EVENT_MARKET_IDENTITY_UNVERIFIED")
    clock = datetime.now(timezone.utc) if now is None else now
    quote, kickoff, current = (_utc_datetime(value)
                               for value in (quote_at, kickoff_at, clock))
    if any(value is None for value in (quote, kickoff, current)):
        return hold("TIMESTAMP_INVALID")
    try:
        age = (current - quote).total_seconds()
        expired = (age < 0 or age > MAX_QUOTE_AGE_SECONDS
                   or current >= kickoff or quote >= kickoff)
    except Exception:
        return hold("TIMESTAMP_INVALID")
    if expired:
        return hold("QUOTE_STALE_OR_EVENT_STARTED")
    ev = odds_value * probability - 1.0
    fair = 1.0 / probability
    if not isfinite(ev) or not isfinite(fair):
        return hold("CALCULATION_NON_FINITE")
    if ev <= MIN_EV:
        return EVDecision("HOLD", "NON_POSITIVE_EV", ev, fair)
    return EVDecision("UNVERIFIED_RESEARCH", "CONDITIONAL_EV_ARITHMETIC_ONLY", ev, fair)
