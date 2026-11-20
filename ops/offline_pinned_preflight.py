"""Strict preflight validation for pinned offline football binary forecast rows.

Reject all invalid records before any walk-forward metric is calculated.
"""
import math
from datetime import datetime, timezone


def _utc(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else None


def validate_pinned_forecast_rows(rows, *, expected_model_version):
    hold = {"status": "HOLD", "reason": "INVALID_PINNED_FORECAST_ROWS",
            "production_recommendations": "DISABLED"}
    if (not isinstance(rows, list) or not 90 <= len(rows) <= 100000
            or not isinstance(expected_model_version, str)
            or not expected_model_version.strip()):
        return hold
    seen = set()
    previous = None
    for row in rows:
        if not isinstance(row, dict):
            return hold
        event = row.get("event_id")
        canonical_event = event.strip() if isinstance(event, str) else None
        p, outcome = row.get("probability"), row.get("outcome")
        predicted = _utc(row.get("predicted_at_utc"))
        kickoff = _utc(row.get("kickoff_at_utc"))
        settled = _utc(row.get("settled_at_utc"))
        if (not isinstance(event, str) or not event.strip() or canonical_event in seen
                or row.get("model_version") != expected_model_version
                or type(p) not in (float, int) or not math.isfinite(p)
                or not 0 <= p <= 1 or type(outcome) is not int
                or outcome not in (0, 1)
                or predicted is None or kickoff is None or settled is None
                or not predicted < kickoff < settled
                or (previous is not None and predicted < previous)):
            return hold
        seen.add(canonical_event)
        previous = predicted
    return {"status": "RESEARCH_ONLY", "reason": "PINNED_ROWS_PREFLIGHT_PASSED",
            "row_count": len(rows), "production_recommendations": "DISABLED"}
