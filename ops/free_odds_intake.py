"""Provider-neutral research quote intake; no network or paid API required.

This validator preserves source provenance but does NOT independently certify
bookmaker execution, odds authenticity, or positive expected value.
"""
from datetime import datetime, timezone
from math import isfinite

PRODUCTION_RECOMMENDATIONS = "DISABLED"

def _time(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_TIMESTAMP")
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("INVALID_TIMESTAMP") from None
    if t.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return t.astimezone(timezone.utc)

def normalize_quote(raw, *, captured_utc):
    """Normalize a documented, timestamped pre-match AH or totals quote.

    Required raw keys: provider, fixture_id, provider_quote_id, bookmaker,
    market, selection, line, decimal_odds, quote_utc.
    """
    if not isinstance(raw, dict):
        raise ValueError("INVALID_QUOTE")
    for k in ("provider", "fixture_id", "provider_quote_id", "bookmaker",
              "market", "selection"):
        if not isinstance(raw.get(k), str) or not raw[k].strip():
            raise ValueError("MISSING_" + k.upper())
    if raw["market"] not in ("ASIAN_HANDICAP", "TOTALS"):
        raise ValueError("UNSUPPORTED_MARKET")
    if raw["market"] == "TOTALS" and raw["selection"] not in ("OVER", "UNDER"):
        raise ValueError("INVALID_SELECTION")
    if raw["market"] == "ASIAN_HANDICAP" and raw["selection"] not in ("HOME", "AWAY"):
        raise ValueError("INVALID_SELECTION")
    odds, line = raw.get("decimal_odds"), raw.get("line")
    if any(type(v) not in (int, float) or not isfinite(v) for v in (odds, line)):
        raise ValueError("INVALID_NUMERIC_VALUE")
    if odds <= 1 or abs(line * 4 - round(line * 4)) > 1e-8:
        raise ValueError("INVALID_ODDS_OR_QUARTER_LINE")
    quote_time, capture_time = _time(raw.get("quote_utc")), _time(captured_utc)
    if quote_time > capture_time:
        raise ValueError("QUOTE_AFTER_CAPTURE")
    return {
        "provider": raw["provider"].strip(),
        "fixture_id": raw["fixture_id"].strip(),
        "provider_quote_id": raw["provider_quote_id"].strip(),
        "bookmaker": raw["bookmaker"].strip(),
        "market": raw["market"],
        "selection": raw["selection"],
        "line": float(line),
        "decimal_odds": float(odds),
        "quote_utc": quote_time.isoformat(),
        "captured_utc": capture_time.isoformat(),
        "quote_authenticity_verified": False,
        "price_executable_verified": False,
        "calibrated_positive_ev": False,
        "production_recommendations": PRODUCTION_RECOMMENDATIONS,
    }
