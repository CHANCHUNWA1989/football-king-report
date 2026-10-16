"""Offline validation of the common research-only reporting format.

This module makes no network calls, betting decisions or brokerage orders.
"""
from datetime import datetime, timezone
import math

REQUIRED = {"system", "generated_at_utc", "source_status", "forecast_count",
            "settled_count", "evaluation_metrics", "failures", "version"}
SYSTEMS = {"football", "basketball", "finance"}

def validate_report(report, *, now=None):
    if not isinstance(report, dict) or not REQUIRED.issubset(report):
        raise ValueError("MISSING_REPORT_FIELDS")
    if not isinstance(report["system"], str) or report["system"] not in SYSTEMS:
        raise ValueError("UNKNOWN_SYSTEM")
    stamp = report["generated_at_utc"]
    if not isinstance(stamp, str):
        raise ValueError("INVALID_TIMESTAMP")
    try:
        dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc
    if dt.tzinfo is None or dt.utcoffset().total_seconds() != 0:
        raise ValueError("TIMESTAMP_NOT_UTC")
    now = datetime.now(timezone.utc) if now is None else now
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    if dt > now:
        raise ValueError("FUTURE_REPORT")
    if not isinstance(report["source_status"], dict):
        raise ValueError("INVALID_SOURCES")
    for source, status in report["source_status"].items():
        if not isinstance(source, str) or not source.strip() or not isinstance(status, str) or status not in ("OK", "DEGRADED", "UNAVAILABLE", "UNKNOWN"):
            raise ValueError("INVALID_SOURCE_STATUS")
    for key in ("forecast_count", "settled_count"):
        if type(report[key]) is not int or report[key] < 0:
            raise ValueError("INVALID_COUNT")
    if report["settled_count"] > report["forecast_count"]:
        raise ValueError("SETTLEMENT_EXCEEDS_FORECASTS")
    metrics = report["evaluation_metrics"]
    if not isinstance(metrics, dict):
        raise ValueError("INVALID_METRICS")
    for value in metrics.values():
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
            raise ValueError("INVALID_METRIC_VALUE")
    if not isinstance(report["failures"], list) or not all(isinstance(x, str) for x in report["failures"]):
        raise ValueError("INVALID_FAILURES")
    if not isinstance(report["version"], str) or not report["version"].strip():
        raise ValueError("INVALID_VERSION")
    return report
