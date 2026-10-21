"""Research-only immutable quote provenance checks; not a live price connector."""
import hashlib
import json
from datetime import datetime, timezone

PRODUCTION_RECOMMENDATIONS = "DISABLED"
REQUIRED = ("fixture_id", "market_id", "source", "source_quote_id",
            "observed_at_utc", "decimal_odds")


def canonical_quote_digest(quote):
    """SHA-256 of canonical, source-identified quote evidence."""
    if not isinstance(quote, dict):
        raise ValueError("INVALID_QUOTE")
    if any(key not in quote for key in REQUIRED):
        raise ValueError("MISSING_PROVENANCE_FIELDS")
    for key in ("fixture_id", "market_id", "source", "source_quote_id"):
        if not isinstance(quote[key], str) or not quote[key].strip():
            raise ValueError("INVALID_PROVENANCE_ID")
    observed = quote["observed_at_utc"]
    if not isinstance(observed, datetime) or observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("INVALID_OBSERVED_TIME")
    from math import isfinite
    odds = quote["decimal_odds"]
    if type(odds) not in (int, float) or not isfinite(odds) or odds <= 1:
        raise ValueError("INVALID_ODDS")
    evidence = {key: quote[key] for key in REQUIRED if key != "observed_at_utc"}
    evidence["observed_at_utc"] = observed.astimezone(timezone.utc).isoformat()
    encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def research_evidence_record(quote):
    """Digest enables tamper detection, not independent bookmaker verification."""
    return {"sha256": canonical_quote_digest(quote),
            "source": quote["source"], "source_quote_id": quote["source_quote_id"],
            "production_recommendations": PRODUCTION_RECOMMENDATIONS}
