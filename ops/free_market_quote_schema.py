"""Offline validation for potential free totals/Asian-handicap data.

This is a schema gate only: no provider is connected and no odds are fetched.
"""
import math
from datetime import datetime, timezone


def parse_utc(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_TIMESTAMP")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return result.astimezone(timezone.utc)


def validate_quote(quote, *, captured_at):
    if not isinstance(quote, dict):
        raise ValueError("INVALID_QUOTE")
    if quote.get("market") not in ("totals", "spreads"):
        raise ValueError("UNSUPPORTED_MARKET")
    if not isinstance(quote.get("fixture_id"), str) or not quote["fixture_id"].strip():
        raise ValueError("MISSING_FIXTURE")
    if not isinstance(quote.get("source"), str) or not quote["source"].strip():
        raise ValueError("MISSING_SOURCE")
    line = quote.get("line")
    if type(line) not in (int, float) or not math.isfinite(line):
        raise ValueError("INVALID_LINE")
    if round(float(line) * 4) != float(line) * 4:
        raise ValueError("INVALID_QUARTER_LINE")
    if quote["market"] == "totals" and not 0 <= line <= 15:
        raise ValueError("INVALID_TOTAL_LINE")
    if quote["market"] == "spreads" and not -15 <= line <= 15:
        raise ValueError("INVALID_HANDICAP_LINE")
    outcomes = quote.get("outcomes")
    required = {"Over", "Under"} if quote["market"] == "totals" else {"Home", "Away"}
    if not isinstance(outcomes, dict) or set(outcomes) != required:
        raise ValueError("INVALID_OUTCOMES")
    if any(type(v) not in (int, float) or not math.isfinite(v) or not 1.01 <= v <= 500
           for v in outcomes.values()):
        raise ValueError("INVALID_PRICES")
    captured = parse_utc(captured_at)
    updated = parse_utc(quote.get("updated_at"))
    kickoff = parse_utc(quote.get("kickoff_at"))
    if updated > captured or (captured - updated).total_seconds() > 1800:
        raise ValueError("STALE_OR_FUTURE_QUOTE")
    if kickoff <= captured:
        raise ValueError("EVENT_ALREADY_STARTED")
    if (kickoff - captured).total_seconds() <= 600:
        raise ValueError("KICKOFF_TOO_CLOSE")
    return {"market": quote["market"], "fixture_id": quote["fixture_id"],
            "status": "SCHEMA_VALID_ONLY", "production_recommendations": "DISABLED"}
