"""Research-only fail-closed gate for synchronising in-play evidence.

This module does not fetch odds, publish picks or unlock production.
"""
from datetime import datetime, timezone
import math


def _utc(value):
    if not isinstance(value, str):
        raise ValueError("timestamp missing")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timezone missing")
    return dt.astimezone(timezone.utc)


def audit_live_snapshot(snapshot, *, max_age_seconds=90):
    """Check that a score, stats and quote refer to one time-valid event.

    A fresh capture time is NOT proof that the upstream data was refreshed.
    This gate intentionally refuses to infer EV or bookmaker intent.
    """
    out = {"status": "HOLD", "production_recommendations": "DISABLED",
           "certified_positive_ev": False, "reasons": []}
    if not isinstance(snapshot, dict):
        out["reasons"].append("INVALID_SNAPSHOT")
        return out
    try:
        event_id = snapshot["event_id"]
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("event id")
        now = _utc(snapshot["decision_utc"])
        kickoff = _utc(snapshot["kickoff_utc"])
        if now < kickoff:
            raise ValueError("NOT_IN_PLAY")
        records = [snapshot[k] for k in ("score", "stats", "quote")]
        if not all(isinstance(r, dict) for r in records):
            raise ValueError("INVALID_RECORD")
        for record in records:
            if record.get("event_id") != event_id:
                raise ValueError("EVENT_ID_MISMATCH")
            source = record.get("source")
            if not isinstance(source, str) or not source.strip():
                raise ValueError("SOURCE_MISSING")
            updated = _utc(record["upstream_updated_utc"])
            captured = _utc(record["captured_utc"])
            if not (kickoff <= updated <= captured <= now):
                raise ValueError("INVALID_TIME_ORDER")
            if (now - updated).total_seconds() > max_age_seconds:
                raise ValueError("STALE_UPSTREAM")
        score = records[0]
        if (type(score.get("home_goals")) is not int or type(score.get("away_goals")) is not int
                or min(score["home_goals"], score["away_goals"]) < 0):
            raise ValueError("INVALID_SCORE")
        stats = records[1]
        for key in ("home_xg", "away_xg"):
            value = stats.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("INVALID_XG")
        quote = records[2]
        if quote.get("market") not in ("totals", "asian_handicap"):
            raise ValueError("UNSUPPORTED_MARKET")
        line = quote.get("line")
        price = quote.get("decimal_price")
        if (type(line) not in (float, int) or not math.isfinite(line)
                or type(price) not in (float, int) or not math.isfinite(price)
                or price <= 1 or abs(line * 4 - round(line * 4)) > 1e-9):
            raise ValueError("INVALID_QUOTE")
        if not isinstance(quote.get("bookmaker"), str) or not quote["bookmaker"].strip():
            raise ValueError("BOOKMAKER_MISSING")
        if quote.get("market") == "totals" and line < 0:
            raise ValueError("INVALID_TOTAL_LINE")
        out["status"] = "RESEARCH_ONLY"
        out["reasons"] = ["SYNCHRONISED_INPUTS_NOT_CALIBRATED_EV"]
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        out["reasons"].append(str(exc) if str(exc) else "INVALID_DATA")
    return out
