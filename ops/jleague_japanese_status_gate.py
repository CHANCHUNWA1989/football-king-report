"""Conservative, offline Japanese match-status triage for J1 research.

This does not fetch/parse source HTML, certify provider independence, or
promote a score, event, xG, market quote or forecast to a verified result.
Use only for explicitly attributed, timestamped *single-source* observations.
"""
import re
from datetime import datetime, timedelta, timezone

MAX_AGE = timedelta(minutes=10)
PERIOD_PATTERN = re.compile(r"(前半|後半)([1-9][0-9]?)分\Z")
EVENT_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


def _timestamp(value):
    if type(value) is not str:
        raise ValueError("MISSING_TIMESTAMP")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc
    if parsed.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return parsed.astimezone(timezone.utc)


def triage(raw_status, *, source_event_id, source_updated_utc,
           captured_utc, as_of_utc):
    """Label a source observation, never certify a live event or score."""
    hold = {
        "status": "HOLD",
        "reason": "INVALID_INPUT",
        "production_recommendations": "DISABLED",
        "model_scoring_eligible": False,
        "independently_authenticated": False,
        "settlement_certified": False,
        "positive_ev_certified": False,
    }
    try:
        if (type(raw_status) is not str or len(raw_status) > 64
                or raw_status != raw_status.strip()):
            raise ValueError("INVALID_RAW_STATUS")
        if (type(source_event_id) is not str
                or EVENT_ID_PATTERN.fullmatch(source_event_id) is None):
            raise ValueError("MISSING_SOURCE_EVENT_ID")
        as_of = _timestamp(as_of_utc)
        captured = _timestamp(captured_utc)
        updated = _timestamp(source_updated_utc)
        if (not timedelta(0) <= as_of - captured <= MAX_AGE
                or not timedelta(0) <= captured - updated <= MAX_AGE
                or not timedelta(0) <= as_of - updated <= MAX_AGE):
            raise ValueError("STALE_OR_FUTURE_SOURCE_TIME")
        if raw_status == "試合前":
            return {**hold, "reason": "PREMATCH_NOT_LIVE",
                    "match_status": "NOT_STARTED"}
        # '試合中' alone cannot identify the half, minute, or event sequence.
        # HT, FT and cancellations require additional independent evidence.
        if raw_status in {"試合中", "試合終了", "前半終了", "ハーフタイム", "中止", "延期"}:
            return {**hold, "reason": "STATUS_REQUIRES_MORE_EVIDENCE"}
        match = PERIOD_PATTERN.fullmatch(raw_status)
        if not match:
            return {**hold, "reason": "UNRECOGNIZED_JAPANESE_STATUS"}
        period, minute_text = match.groups()
        minute = int(minute_text)
        if minute > 70:
            return {**hold, "reason": "IMPLAUSIBLE_PERIOD_MINUTE"}
        return {
            "status": "RESEARCH_ONLY",
            "reason": "SINGLE_SOURCE_MINUTE_NOT_AUTHENTICATED",
            "match_status": "FIRST_HALF" if period == "前半" else "SECOND_HALF",
            "period_minute": minute,
            "source_event_id": source_event_id,
            "source_updated_utc": updated.isoformat(),
            "production_recommendations": "DISABLED",
            "model_scoring_eligible": False,
            "independently_authenticated": False,
            "settlement_certified": False,
            "positive_ev_certified": False,
        }
    except (ValueError, OverflowError, TypeError) as exc:
        return {**hold, "reason": str(exc)}
