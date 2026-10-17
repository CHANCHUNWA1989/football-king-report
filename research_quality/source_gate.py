"""Offline source-quality gates shared by sports and market research.

This module never downloads data or authorizes bets/trades.
"""
from datetime import datetime, timezone
import math


def _utc(value):
    if not isinstance(value, str):
        raise ValueError("TIMESTAMP_REQUIRED")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return dt.astimezone(timezone.utc)


def validate_source_record(record, *, now_utc, max_age_seconds=86400):
    """Validate a source snapshot, rejecting stale/future/ambiguous records.

    Required fields: source, observed_at, event_id, event_at.
    observed_at is the *upstream observation* time, not local download time.
    """
    if not isinstance(record, dict):
        raise ValueError("INVALID_RECORD")
    for key in ("source", "event_id"):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise ValueError("MISSING_" + key.upper())
    if not isinstance(max_age_seconds, (int, float)) or not math.isfinite(max_age_seconds) or max_age_seconds <= 0:
        raise ValueError("INVALID_MAX_AGE")
    now = _utc(now_utc)
    observed = _utc(record.get("observed_at"))
    event = _utc(record.get("event_at"))
    if observed > now:
        raise ValueError("FUTURE_SOURCE")
    if (now - observed).total_seconds() > max_age_seconds:
        raise ValueError("STALE_SOURCE")
    if observed >= event:
        raise ValueError("POST_EVENT_SOURCE")
    return True


def validate_probabilities(values, *, tolerance=0.002):
    """Validate a complete mutually-exclusive probability distribution."""
    if not isinstance(values, (list, tuple)) or len(values) < 2:
        raise ValueError("INVALID_DISTRIBUTION")
    if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in values):
        raise ValueError("INVALID_PROBABILITY")
    if abs(sum(values) - 1.0) > tolerance:
        raise ValueError("PROBABILITIES_NOT_NORMALIZED")
    return True
