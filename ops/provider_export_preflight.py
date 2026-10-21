"""Strict preflight validation for offline football odds export.

No claims of provider authenticity or price execution. Invalid input is
rejected before report generation, not silently converted into betting picks.
"""
from datetime import datetime, timezone
from math import isfinite

def _utc(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_TIMESTAMP")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("INVALID_TIMESTAMP") from None
    if result.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return result.astimezone(timezone.utc)

def validate_export(export, *, generated_utc):
    now = _utc(generated_utc)
    if not isinstance(export, dict) or not isinstance(export.get("source"), str) or not export["source"].strip():
        raise ValueError("MISSING_SOURCE")
    fixtures = export.get("fixtures")
    if not isinstance(fixtures, list):
        raise ValueError("INVALID_FIXTURES")
    seen_fixtures = set()
    seen_quotes = set()
    for f in fixtures:
        if not isinstance(f, dict):
            raise ValueError("INVALID_FIXTURE")
        for field in ("id", "home", "away"):
            if not isinstance(f.get(field), str) or not f[field].strip():
                raise ValueError("MISSING_" + field.upper())
        if f["id"] in seen_fixtures:
            raise ValueError("DUPLICATE_FIXTURE")
        seen_fixtures.add(f["id"])
        if f["home"].strip().casefold() == f["away"].strip().casefold():
            raise ValueError("SAME_TEAM")
        kickoff = _utc(f.get("kickoff_utc"))
        if kickoff <= now:
            raise ValueError("FIXTURE_ALREADY_STARTED")
        quotes = f.get("quotes")
        if not isinstance(quotes, list):
            raise ValueError("INVALID_QUOTES")
        for q in quotes:
            if not isinstance(q, dict):
                raise ValueError("INVALID_QUOTE")
            for field in ("id", "bookmaker", "market", "selection"):
                if not isinstance(q.get(field), str) or not q[field].strip():
                    raise ValueError("MISSING_QUOTE_" + field.upper())
            key = (f["id"], q["id"])
            if key in seen_quotes:
                raise ValueError("DUPLICATE_QUOTE_ID")
            seen_quotes.add(key)
            market, selection = q["market"], q["selection"]
            if market not in ("ASIAN_HANDICAP", "TOTALS"):
                raise ValueError("UNSUPPORTED_MARKET")
            if selection not in (("HOME", "AWAY") if market == "ASIAN_HANDICAP" else ("OVER", "UNDER")):
                raise ValueError("INVALID_SELECTION")
            line, odds = q.get("line"), q.get("decimal_odds")
            if any(type(v) not in (int, float) or not isfinite(v) for v in (line, odds)):
                raise ValueError("INVALID_NUMERIC_VALUE")
            if odds <= 1 or abs(line * 4 - round(line * 4)) > 1e-8:
                raise ValueError("INVALID_ODDS_OR_LINE")
            quote_time = _utc(q.get("quote_utc"))
            if quote_time > now:
                raise ValueError("QUOTE_IN_FUTURE")
            if quote_time >= kickoff:
                raise ValueError("QUOTE_NOT_PREMATCH")
    return {"fixture_count": len(fixtures), "quote_count": len(seen_quotes),
            "preflight_passed": True, "provider_authenticity_verified": False,
            "production_recommendations": "HOLD"}
