"""Fail-closed prospective evidence chain for research forecasts and results.

This module validates attestations supplied by independent collectors. It cannot
itself certify that a provider or capture timestamp is authentic.
"""
import hashlib
import json
from datetime import datetime


def _instant(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_TIMESTAMP")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("BAD_TIMESTAMP") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return dt


def _sha(value):
    return (isinstance(value, str) and len(value) == 64
            and all(ch in "0123456789abcdef" for ch in value))


def validate_prospective_chain(record):
    """Return HOLD diagnostic, never a permission to recommend bets."""
    reasons = []
    if not isinstance(record, dict):
        return {"status": "HOLD", "production_recommendations": "DISABLED",
                "valid_evidence_chain": False, "reasons": ["NOT_AN_OBJECT"]}
    required_text = ("event_id", "provider_event_id", "model_version",
                     "market", "bookmaker", "result_provider",
                     "result_provider_event_id")
    for key in required_text:
        if not isinstance(record.get(key), str) or not record[key].strip():
            reasons.append("MISSING_" + key.upper())
    for key in ("model_sha256", "forecast_payload_sha256", "odds_payload_sha256",
                "result_payload_sha256"):
        if not _sha(record.get(key)):
            reasons.append("INVALID_" + key.upper())
    if record.get("production_recommendations") != "DISABLED":
        reasons.append("UNSAFE_RECOMMENDATION_STATUS")
    if record.get("source_result_independently_verified") is not True:
        reasons.append("RESULT_NOT_INDEPENDENTLY_VERIFIED")
    try:
        forecast = _instant(record.get("forecast_captured_utc"))
        odds = _instant(record.get("odds_captured_utc"))
        kickoff = _instant(record.get("kickoff_utc"))
        result = _instant(record.get("result_captured_utc"))
        if not (forecast < kickoff and odds < kickoff and result > kickoff):
            reasons.append("INVALID_EVENT_CHRONOLOGY")
    except ValueError as exc:
        reasons.append(str(exc))
    if not isinstance(record.get("forecast_source_commit"), str) or len(record.get("forecast_source_commit", "")) < 7:
        reasons.append("MISSING_FORECAST_SOURCE_COMMIT")
    return {"status": "HOLD", "production_recommendations": "DISABLED",
            "valid_evidence_chain": not reasons,
            "reasons": sorted(set(reasons)),
            "warning": "Structural checks only. Independent custody/provider verification remains mandatory."}


def payload_sha256(payload):
    """Hash exact provider bytes, not reconstructed/normalized JSON."""
    if not isinstance(payload, bytes):
        raise TypeError("raw payload bytes required")
    return hashlib.sha256(payload).hexdigest()


def canonical_record_sha256(record):
    if not isinstance(record, dict):
        raise TypeError("record object required")
    return hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
