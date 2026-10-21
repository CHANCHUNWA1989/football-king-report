"""Fail-closed, research-only eligibility gate for an Asian EV quote.

This gate does not certify model calibration, independent price evidence or ROI.
"""
from datetime import datetime, timezone
from math import isfinite

MAX_QUOTE_AGE_SECONDS = 300
PRODUCTION_RECOMMENDATIONS = "DISABLED"


def assess_quote(quote, *, now_utc, kickoff_utc):
    """Return a deterministic research-only eligibility decision."""
    reasons = []
    if not isinstance(quote, dict):
        return {"eligible_for_research": False, "reasons": ["INVALID_QUOTE"],
                "production_recommendations": PRODUCTION_RECOMMENDATIONS}
    for label, value in (("now", now_utc), ("kickoff", kickoff_utc),
                         ("observed", quote.get("observed_at_utc"))):
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            reasons.append("INVALID_" + label.upper() + "_TIME")
    if any(reason.startswith("INVALID_") for reason in reasons):
        return {"eligible_for_research": False, "reasons": reasons,
                "production_recommendations": PRODUCTION_RECOMMENDATIONS}
    now = now_utc.astimezone(timezone.utc)
    kickoff = kickoff_utc.astimezone(timezone.utc)
    observed = quote["observed_at_utc"].astimezone(timezone.utc)
    if not isinstance(quote.get("fixture_id"), str) or not quote["fixture_id"].strip():
        reasons.append("MISSING_FIXTURE_ID")
    if not isinstance(quote.get("market_id"), str) or not quote["market_id"].strip():
        reasons.append("MISSING_MARKET_ID")
    if not isinstance(quote.get("source"), str) or not quote["source"].strip():
        reasons.append("MISSING_SOURCE")
    odds = quote.get("decimal_odds")
    if type(odds) not in (int, float) or not isfinite(odds) or odds <= 1:
        reasons.append("INVALID_ODDS")
    if now >= kickoff:
        reasons.append("MATCH_ALREADY_STARTED")
    if observed >= kickoff:
        reasons.append("NOT_PREMATCH_QUOTE")
    age = (now - observed).total_seconds()
    if age < 0:
        reasons.append("FUTURE_QUOTE")
    if age > MAX_QUOTE_AGE_SECONDS:
        reasons.append("STALE_QUOTE")
    return {"eligible_for_research": not reasons, "reasons": reasons,
            "production_recommendations": PRODUCTION_RECOMMENDATIONS}
