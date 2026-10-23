"""Cross-check live match state with a fresh authorized market quote."""
from datetime import datetime, timezone
from live_quote_gate import assess_quote, _utc


def assess_snapshot(score, quote, *, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(score, dict) or not isinstance(quote, dict):
        return {"status": "HOLD", "reason": "MISSING_FEED"}
    event = score.get("source_event_id")
    if not isinstance(event, str) or not event or event != quote.get("source_event_id"):
        return {"status": "HOLD", "reason": "EVENT_MISMATCH"}
    if score.get("source_authorized") is not True or score.get("status") != "LIVE":
        return {"status": "HOLD", "reason": "UNVERIFIED_OR_NOT_LIVE"}
    for field, ceiling in (("minute", 130), ("home_goals", 30), ("away_goals", 30)):
        value = score.get(field)
        if type(value) is not int or not 0 <= value <= ceiling:
            return {"status": "HOLD", "reason": "INVALID_MATCH_STATE"}
    updated = _utc(score.get("source_last_update_utc"))
    if updated is None or not isinstance(now, datetime) or now.tzinfo is None:
        return {"status": "HOLD", "reason": "INVALID_SCORE_TIME"}
    age = (now.astimezone(timezone.utc) - updated).total_seconds()
    if age < -30 or age > 90:
        return {"status": "HOLD", "reason": "STALE_SCORE"}
    result = assess_quote(quote, now=now, live=True)
    if result["status"] != "RESEARCH_ONLY":
        return result
    return {"status": "RESEARCH_ONLY", "reason": "SYNCHRONIZED_RESEARCH",
            "production_recommendations": "DISABLED"}
