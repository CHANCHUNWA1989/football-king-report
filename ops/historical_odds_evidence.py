"""Fail-closed evidence gate for settled, research-only historical odds.

This does not verify a bookmaker's claim independently. It requires a
traceable provider event, time and explicit executable-price evidence
before allowing a row to be considered for later independent audit.
"""
from datetime import datetime, timezone
from math import isfinite

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
    """Reject missing source/quote evidence, late quotes and invented prices."""
    if not isinstance(row, dict):
        raise ValueError("INVALID_ROW")
    for key in ("fixture_id", "provider", "market", "selection",
                "provider_quote_id", "evidence_uri"):
        if not isinstance(row.get(key), str) or not row[key].strip():
            raise ValueError("MISSING_" + key.upper())
    if not row["evidence_uri"].startswith(("https://", "http://")):
        raise ValueError("INVALID_EVIDENCE_URI")
    if row.get("settlement_basis") not in ("FULL_MATCH", "REMAINDER"):
        raise ValueError("UNKNOWN_SETTLEMENT_BASIS")
    price = row.get("decimal_odds")
    if type(price) not in (int, float) or not isfinite(price) or price <= 1:
        raise ValueError("INVALID_ODDS")
    if row.get("price_was_executable") is not True:
        raise ValueError("UNVERIFIED_EXECUTABLE_PRICE")
    quote = _utc(row.get("quote_utc"))
    decision = _utc(row.get("decision_utc"))
    kickoff = _utc(row.get("kickoff_utc"))
    if not quote <= decision < kickoff and row.get("market_phase") == "PREMATCH":
        raise ValueError("PREMATCH_TIME_LEAK")
    if row.get("market_phase") not in ("PREMATCH", "INPLAY"):
        raise ValueError("UNKNOWN_MARKET_PHASE")
    if row["market_phase"] == "INPLAY" and not quote <= decision:
        raise ValueError("INPLAY_TIME_LEAK")
    return {
        "fixture_id": row["fixture_id"],
        "provider_quote_id": row["provider_quote_id"],
        "evidence_uri": row["evidence_uri"],
        "settlement_basis": row["settlement_basis"],
        "status": "EVIDENCE_PRESENT_NOT_INDEPENDENTLY_VERIFIED",
        "production_recommendations": PRODUCTION_RECOMMENDATIONS,
    }
