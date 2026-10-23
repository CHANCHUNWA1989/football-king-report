"""Fail-closed provenance and freshness gate for football market research.

Research only: passing this gate never constitutes a betting recommendation.
"""
from datetime import datetime, timezone


def _utc(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def assess_quote(quote, *, now=None, live=False, max_age_seconds=120):
    """Validate independently timestamped, identifiable bookmaker quotes.

    The free pre-match consensus feed must not be represented as live,
    executable bookmaker prices. Returns a safe status, never an EV.
    """
    if not isinstance(quote, dict):
        return {"status": "HOLD", "reason": "INVALID_QUOTE"}
    if quote.get("probabilities_are_no_vig_consensus") is True:
        return {"status": "HOLD", "reason": "CONSENSUS_NOT_EXECUTABLE"}
    if live and quote.get("is_live") is not True:
        return {"status": "HOLD", "reason": "NOT_LIVE"}
    if not all(isinstance(quote.get(k), str) and quote[k].strip()
               for k in ("source_event_id", "bookmaker", "market", "selection")):
        return {"status": "HOLD", "reason": "MISSING_IDENTITY"}
    stamp = _utc(quote.get("market_last_update_utc"))
    current = now or datetime.now(timezone.utc)
    if stamp is None or current.tzinfo is None:
        return {"status": "HOLD", "reason": "MISSING_OR_INVALID_SOURCE_TIME"}
    age = (current.astimezone(timezone.utc) - stamp).total_seconds()
    if age < -30:
        return {"status": "HOLD", "reason": "FUTURE_SOURCE_TIME"}
    if age > max_age_seconds:
        return {"status": "HOLD", "reason": "STALE_QUOTE"}
    price = quote.get("decimal_odds")
    if type(price) not in (float, int) or not 1.01 <= price <= 500:
        return {"status": "HOLD", "reason": "INVALID_PRICE"}
    if quote.get("source_authorized") is not True:
        return {"status": "HOLD", "reason": "UNVERIFIED_SOURCE_RIGHTS"}
    return {"status": "RESEARCH_ONLY", "reason": "FRESH_VERIFIED_QUOTE"}
