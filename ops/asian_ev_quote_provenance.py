"""Research-only immutable quote provenance checks; not a live price connector."""
import hashlib
import json
from datetime import datetime, timezone
from math import isfinite

PRODUCTION_RECOMMENDATIONS = "DISABLED"
SCHEMA = "football-king-quote-evidence-v2"
REQUIRED = ("fixture_id", "market_id", "source", "source_quote_id",
            "observed_at_utc", "decimal_odds", "bookmaker_id", "market_type",
            "selection", "line", "bookmaker_updated_at_utc", "kickoff_utc")
TIME_FIELDS = ("bookmaker_updated_at_utc", "observed_at_utc", "kickoff_utc")


def _finite_number(value):
    try:
        return type(value) in (int, float) and isfinite(value)
    except OverflowError:
        return False


def canonical_quote_digest(quote):
    """Bind a complete v2 research quote; never authenticate its source.

    observed_at_utc is response completion; kickoff_utc is the recorded schedule,
    not proof of actual kickoff. Legacy six-field inputs are rejected, not upgraded.
    """
    if not isinstance(quote, dict):
        raise ValueError("INVALID_QUOTE")
    if any(key not in quote for key in REQUIRED):
        raise ValueError("MISSING_PROVENANCE_FIELDS")
    if set(quote) != set(REQUIRED):
        raise ValueError("UNKNOWN_PROVENANCE_FIELDS")
    for key in ("fixture_id", "market_id", "source", "source_quote_id", "bookmaker_id"):
        if not isinstance(quote[key], str) or not quote[key].strip():
            raise ValueError("INVALID_PROVENANCE_ID")
    times = {}
    for key in TIME_FIELDS:
        value = quote[key]
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("INVALID_PROVENANCE_TIME")
        try:
            times[key] = value.astimezone(timezone.utc)
        except (OverflowError, ValueError) as exc:
            raise ValueError("INVALID_PROVENANCE_TIME") from exc
    if not times["bookmaker_updated_at_utc"] <= times["observed_at_utc"] < times["kickoff_utc"]:
        raise ValueError("INVALID_QUOTE_TIME_ORDER")
    odds = quote["decimal_odds"]
    if not _finite_number(odds) or odds <= 1:
        raise ValueError("INVALID_ODDS")
    market = quote["market_type"]
    selections = {"h2h": ("HOME", "DRAW", "AWAY"),
                  "spreads": ("HOME", "AWAY"), "totals": ("OVER", "UNDER")}
    if not isinstance(market, str) or market not in selections or quote["selection"] not in selections[market]:
        raise ValueError("INVALID_MARKET_SELECTION")
    line = quote["line"]
    if market == "h2h":
        if line is not None:
            raise ValueError("INVALID_LINE")
    elif (not _finite_number(line)
          or not _finite_number(line * 4) or (line * 4) % 1 != 0
          or (market == "totals" and line < 0)):
        raise ValueError("INVALID_LINE")
    evidence = {key: quote[key] for key in REQUIRED if key not in TIME_FIELDS}
    evidence.update({key: value.isoformat() for key, value in times.items()})
    evidence["schema"] = SCHEMA
    encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def research_evidence_record(quote):
    """Digest enables tamper detection, not independent bookmaker verification."""
    return {"schema": SCHEMA, "sha256": canonical_quote_digest(quote),
            "independently_verified": False,
            "source": quote["source"], "source_quote_id": quote["source_quote_id"],
            "production_recommendations": PRODUCTION_RECOMMENDATIONS}
