"""Validate an externally provided pinned source receipt.

This checks consistency only. Caller must obtain the receipt via an independently
trusted channel and authenticate the issuer outside this module.
"""
import json
import re
from datetime import datetime, timezone


def _parse_utc(value):
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp.astimezone(timezone.utc) if stamp.tzinfo else None


def validate_source_receipt(receipt, *, expected_history_sha256,
                            expected_manifest_sha256, expected_model_version):
    hold = {"status": "HOLD", "reason": "INVALID_EXTERNAL_SOURCE_RECEIPT",
            "production_recommendations": "DISABLED"}
    if not isinstance(receipt, dict) or set(receipt) != {
        "schema_version", "issuer", "issued_at_utc", "history_sha256",
        "capture_manifest_sha256", "model_version", "reference_id"
    }:
        return hold
    if (receipt["schema_version"] != 1
            or not isinstance(receipt["issuer"], str)
            or not receipt["issuer"].strip()
            or not isinstance(receipt["reference_id"], str)
            or not receipt["reference_id"].strip()
            or _parse_utc(receipt["issued_at_utc"]) is None
            or not isinstance(expected_history_sha256, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", expected_history_sha256) is None
            or not isinstance(expected_manifest_sha256, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", expected_manifest_sha256) is None
            or receipt["history_sha256"] != expected_history_sha256.lower()
            or receipt["capture_manifest_sha256"] != expected_manifest_sha256.lower()
            or receipt["model_version"] != expected_model_version):
        return hold
    return {"status": "RESEARCH_ONLY", "reason": "RECEIPT_FIELDS_CONSISTENT",
            "issuer": receipt["issuer"], "reference_id": receipt["reference_id"],
            "issuer_identity_verified": False, "signature_verified": False,
            "trusted_timestamp_authority_verified": False,
            "production_recommendations": "DISABLED"}
