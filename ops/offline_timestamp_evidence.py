"""Fail-closed integrity checks for externally captured timestamp evidence.

A matching digest does not authenticate a clock, issuer, or pre-match capture.
The expected digest must be obtained from an independent trusted channel.
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def _utc(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def validate_timestamp_evidence(path, *, expected_sha256,
                                expected_history_sha256,
                                expected_manifest_sha256):
    hold = {"status": "HOLD", "reason": "INVALID_TIMESTAMP_EVIDENCE",
            "trusted_timestamp_authority_verified": False,
            "production_recommendations": "DISABLED"}
    if (not isinstance(path, (str, Path))
            or not isinstance(expected_sha256, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256) is None):
        return hold
    try:
        source = Path(path)
        if source.stat().st_size > 100_000:
            return hold
        with source.open("rb") as stream:
            raw = stream.read(100_001)
        if len(raw) > 100_000 or hashlib.sha256(raw).hexdigest() != expected_sha256.lower():
            return hold
        def no_duplicates(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate key")
                result[key] = value
            return result
        evidence = json.loads(raw, object_pairs_hook=no_duplicates,
                              parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
    except (OSError, ValueError, TypeError, RecursionError, UnicodeDecodeError):
        return hold
    if (not isinstance(evidence, dict)
            or set(evidence) != {"schema_version", "authority", "observed_at_utc",
                                "history_sha256", "capture_manifest_sha256", "reference_id"}
            or type(evidence["schema_version"]) is not int
            or evidence["schema_version"] != 1
            or not isinstance(evidence["authority"], str)
            or not evidence["authority"].strip()
            or not isinstance(evidence["reference_id"], str)
            or not evidence["reference_id"].strip()
            or _utc(evidence["observed_at_utc"]) is None
            or evidence["history_sha256"] != expected_history_sha256
            or evidence["capture_manifest_sha256"] != expected_manifest_sha256):
        return hold
    return {"status": "RESEARCH_ONLY", "reason": "TIMESTAMP_EVIDENCE_FIELDS_PINNED",
            "observed_at_utc": evidence["observed_at_utc"],
            "reference_id": evidence["reference_id"],
            "trusted_timestamp_authority_verified": False,
            "production_recommendations": "DISABLED"}
