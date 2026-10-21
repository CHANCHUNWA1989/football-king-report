"""Fail-closed evidence gate for historical research odds.

A claimed executable quote and an evidence link are *not* independent
verification. This module never authorizes production recommendations.
"""
from datetime import datetime, timezone
from math import isfinite
from urllib.parse import urlsplit

PRODUCTION_RECOMMENDATIONS = "DISABLED"

def _utc(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_TIMESTAMP")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("INVALID_TIMESTAMP") from None
    if dt.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return dt.astimezone(timezone.utc)

def validate_historical_price(row):
    """Validate mandatory quote provenance and chronology, not authenticity."""
    if not isinstance(row, dict):
        raise ValueError("INVALID_ROW")
    for key in ("fixture_id", "provider", "market", "selection",
                "provider_quote_id", "evidence_uri"):
        if not isinstance(row.get(key), str) or not row[key].strip():
            raise ValueError("MISSING_" + key.upper())
    url = urlsplit(row["evidence_uri"])
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("INVALID_EVIDENCE_URI")
    if row.get("settlement_basis") not in ("FULL_MATCH", "REMAINDER"):
        raise ValueError("UNKNOWN_SETTLEMENT_BASIS")
    price = row.get("decimal_odds")
    if type(price) not in (int, float) or not isfinite(price) or price <= 1:
        raise ValueError("INVALID_ODDS")
    if row.get("price_was_executable") is not True:
        raise ValueError("UNVERIFIED_EXECUTABLE_PRICE")
    phase = row.get("market_phase")
    if phase not in ("PREMATCH", "INPLAY"):
        raise ValueError("UNKNOWN_MARKET_PHASE")
    quote = _utc(row.get("quote_utc"))
    decision = _utc(row.get("decision_utc"))
    kickoff = _utc(row.get("kickoff_utc"))
    if phase == "PREMATCH" and not quote <= decision < kickoff:
        raise ValueError("PREMATCH_TIME_LEAK")
    if phase == "INPLAY" and not kickoff <= quote <= decision:
        raise ValueError("INPLAY_TIME_LEAK")
    if phase == "INPLAY":
        for key in ("match_minute", "home_goals", "away_goals"):
            value = row.get(key)
            if type(value) is not int or value < 0:
                raise ValueError("MISSING_INPLAY_STATE")
        if row["match_minute"] > 130:
            raise ValueError("INVALID_MATCH_MINUTE")
    return {
        "fixture_id": row["fixture_id"],
        "provider_quote_id": row["provider_quote_id"],
        "evidence_uri": row["evidence_uri"],
        "settlement_basis": row["settlement_basis"],
        "status": "EVIDENCE_PRESENT_NOT_INDEPENDENTLY_VERIFIED",
        "production_recommendations": PRODUCTION_RECOMMENDATIONS,
    }
