"""Validate bookmaker-level timestamps in historical odds API responses.

Research only: timestamps and licensing still require independent verification.
"""
from datetime import datetime, timezone
from ops.the_odds_api_adapter import extract_historical_quotes

PRODUCTION_RECOMMENDATIONS = "DISABLED"
POSITIVE_EV_VERIFIED = False

def _time(value):
    if not isinstance(value, str):
        raise ValueError("missing ISO timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid ISO timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return result.astimezone(timezone.utc)

def extract_verified_time_quotes(envelope, *, max_bookmaker_age_minutes=30):
    """Fail closed if provider bookmaker/market timestamps are missing or stale.

    The word 'verified' here means only internally consistent timestamp fields,
    not independently authenticated provider data.
    """
    if not isinstance(max_bookmaker_age_minutes, (int, float)) or isinstance(max_bookmaker_age_minutes, bool) or not 0 < max_bookmaker_age_minutes <= 1440:
        raise ValueError("invalid maximum age")
    if not isinstance(envelope, dict) or not isinstance(envelope.get("data"), list):
        raise ValueError("invalid envelope")
    captured = _time(envelope.get("timestamp"))
    for event in envelope["data"]:
        kickoff = _time(event.get("commence_time"))
        if captured >= kickoff:
            continue
        for bookmaker in event.get("bookmakers", []):
            updated = _time(bookmaker.get("last_update"))
            if updated > captured:
                raise ValueError("bookmaker update occurs after snapshot")
            if (captured-updated).total_seconds() > max_bookmaker_age_minutes*60:
                raise ValueError("stale bookmaker update")
            for market in bookmaker.get("markets", []):
                if market.get("key") not in ("spreads", "totals"):
                    continue
                market_updated = _time(market.get("last_update"))
                if market_updated > captured:
                    raise ValueError("market update occurs after snapshot")
                if (captured-market_updated).total_seconds() > max_bookmaker_age_minutes*60:
                    raise ValueError("stale market update")
    quotes = extract_historical_quotes(envelope)
    # Attach raw source timestamps to every returned quote for revalidation.
    for event in envelope["data"]:
        if captured >= _time(event.get("commence_time")):
            continue
        for bookmaker in event.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                if market.get("key") not in ("spreads", "totals"):
                    continue
                # Quotes can share event/bookmaker/market, but freshness timestamps
                # must be consistent for every matching source entry.
                for quote in quotes:
                    if (quote["event_id"] == event["id"]
                        and quote["bookmaker"] == bookmaker["key"]
                        and quote["market"] == ("total" if market["key"] == "totals" else "handicap")):
                        quote["bookmaker_last_update"] = bookmaker["last_update"]
                        quote["market_last_update"] = market["last_update"]
    for quote in quotes:
        quote["bookmaker_timestamp_checked"] = True
        quote["source_authenticity_verified"] = False
        quote["production_recommendation_allowed"] = False
    return quotes
