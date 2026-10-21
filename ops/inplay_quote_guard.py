"""Fail-closed provenance validation for research-only in-play market quotes."""
from datetime import datetime, timezone

ALLOWED_BASIS = {"FULL_MATCH", "REMAINDER"}
PRODUCTION_RECOMMENDATIONS = "DISABLED"

def _time(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_TIMESTAMP")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("INVALID_TIMESTAMP") from None
    if stamp.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return stamp.astimezone(timezone.utc)

def validate_inplay_quote(quote, *, decision_utc, max_age_seconds=90):
    """Validate identity, event time, quote time, and settlement basis.

    This is only a provenance gate; it cannot prove an offered price was
    executable or that the model is calibrated.
    """
    if not isinstance(quote, dict):
        raise ValueError("INVALID_QUOTE")
    if not isinstance(quote.get("match_id"), str) or not quote["match_id"].strip():
        raise ValueError("MISSING_MATCH_ID")
    if not isinstance(quote.get("source"), str) or not quote["source"].strip():
        raise ValueError("MISSING_SOURCE")
    if quote.get("settlement_basis") not in ALLOWED_BASIS:
        raise ValueError("UNKNOWN_SETTLEMENT_BASIS")
    if type(quote.get("minute")) is not int or not 0 <= quote["minute"] <= 130:
        raise ValueError("INVALID_MATCH_MINUTE")
    if type(quote.get("home_goals")) is not int or quote["home_goals"] < 0:
        raise ValueError("INVALID_SCORE")
    if type(quote.get("away_goals")) is not int or quote["away_goals"] < 0:
        raise ValueError("INVALID_SCORE")
    if type(max_age_seconds) not in (int, float) or not 0 < max_age_seconds <= 600:
        raise ValueError("INVALID_MAX_AGE")
    decision = _time(decision_utc)
    captured = _time(quote.get("captured_utc"))
    updated = _time(quote.get("provider_updated_utc"))
    if not updated <= captured <= decision:
        raise ValueError("INCONSISTENT_QUOTE_TIMELINE")
    if (decision - updated).total_seconds() > max_age_seconds:
        raise ValueError("STALE_QUOTE")
    return {
        "match_id": quote["match_id"],
        "source": quote["source"],
        "settlement_basis": quote["settlement_basis"],
        "minute": quote["minute"],
        "score": [quote["home_goals"], quote["away_goals"]],
        "provider_updated_utc": updated.isoformat(),
        "captured_utc": captured.isoformat(),
        "decision_utc": decision.isoformat(),
        "status": "RESEARCH_ONLY",
        "production_recommendations": PRODUCTION_RECOMMENDATIONS,
    }
