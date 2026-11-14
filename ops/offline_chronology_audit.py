"""Fail-closed chronological audit of historical pre-match forecast rows.

A timestamp check cannot prove an external record is authentic; source provenance
and immutable capture must be verified separately before performance claims.
"""
from datetime import datetime, timezone
from offline_calibration_report import evaluate_binary_calibration


def _parse_utc(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo is not None else None


def evaluate_chronological_history(rows, *, bins=10):
    hold = {"status": "HOLD", "reason": "UNVERIFIED_FORECAST_CHRONOLOGY",
            "production_recommendations": "DISABLED"}
    if not isinstance(rows, list) or not 30 <= len(rows) <= 100000:
        return hold
    ordered = []
    for row in rows:
        if not isinstance(row, dict):
            return hold
        predicted = _parse_utc(row.get("predicted_at_utc"))
        kickoff = _parse_utc(row.get("kickoff_at_utc"))
        settled = _parse_utc(row.get("settled_at_utc"))
        if (predicted is None or kickoff is None or settled is None
                or not predicted < kickoff < settled):
            return hold
        ordered.append((predicted, row))
    if any(ordered[i][0] > ordered[i + 1][0] for i in range(len(ordered) - 1)):
        return hold
    result = evaluate_binary_calibration(
        [{"event_id": row.get("event_id"), "probability": row.get("probability"),
          "outcome": row.get("outcome")} for _, row in ordered], bins=bins)
    if result["status"] != "RESEARCH_ONLY":
        return result
    return {**result, "reason": "CHRONOLOGICAL_OFFLINE_DIAGNOSTIC",
            "timestamp_order_checked": True, "source_authenticity_verified": False}
