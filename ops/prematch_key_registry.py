"""Pinned key registry with bounded validity and explicit revocation.

Registry must be delivered through an independently authenticated channel.
"""
from datetime import datetime, timezone
from prematch_trusted_receipt import _time, verify_receipt


def verify_with_registry(raw, receipt, *, registry, expected_provider,
                         trusted_clock=None):
    hold = {"status": "HOLD", "signature_verified": False,
            "trusted_timestamp_verified": False,
            "production_recommendations": "DISABLED"}
    if not isinstance(registry, dict) or not isinstance(receipt, dict):
        return {**hold, "rejection_reasons": ["INVALID_KEY_REGISTRY"]}
    key_id = receipt.get("key_id")
    record = registry.get(key_id)
    if not isinstance(record, dict) or set(record) != {
            "public_key_pem", "provider_id", "valid_from_utc",
            "valid_until_utc", "revoked"}:
        return {**hold, "rejection_reasons": ["KEY_NOT_REGISTERED"]}
    if record["revoked"] is not False:
        return {**hold, "rejection_reasons": ["KEY_REVOKED"]}
    if record["provider_id"] != expected_provider:
        return {**hold, "rejection_reasons": ["KEY_PROVIDER_MISMATCH"]}
    try:
        captured = _time(receipt["captured_at_utc"])
        start = _time(record["valid_from_utc"])
        end = _time(record["valid_until_utc"])
        if not start <= captured < end or start >= end:
            raise ValueError("out of key validity window")
    except (KeyError, ValueError, TypeError, OverflowError):
        return {**hold, "rejection_reasons": ["KEY_OUTSIDE_VALIDITY"]}
    return verify_receipt(raw, receipt,
                          pinned_keys={key_id: record["public_key_pem"]},
                          expected_provider=expected_provider,
                          trusted_clock=trusted_clock)
