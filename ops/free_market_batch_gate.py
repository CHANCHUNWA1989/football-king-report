"""Offline batch gate for candidate totals/spreads quotes; never fetches data.

Validation is not provider approval or production authorization.
"""
from ops.free_market_quote_schema import validate_quote


def validate_batch(quotes, *, captured_at):
    if not isinstance(quotes, list) or not quotes:
        return {"status": "HOLD", "reason": "NO_QUOTES", "accepted": 0}
    seen = set()
    markets = set()
    for quote in quotes:
        try:
            result = validate_quote(quote, captured_at=captured_at)
        except (ValueError, TypeError, KeyError):
            return {"status": "HOLD", "reason": "INVALID_QUOTE", "accepted": 0}
        key = (quote["source"], result["fixture_id"], result["market"], quote["line"])
        if key in seen:
            return {"status": "HOLD", "reason": "DUPLICATE_MARKET_LINE", "accepted": 0}
        seen.add(key)
        markets.add(result["market"])
    return {"status": "SCHEMA_VALID_ONLY", "accepted": len(seen),
            "markets": sorted(markets), "production_recommendations": "DISABLED"}
