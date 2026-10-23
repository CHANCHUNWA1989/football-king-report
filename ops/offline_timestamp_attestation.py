"""Fail-closed third-party timestamp attestation preflight.

This is deliberately NOT an RFC 3161 validator. An arbitrary claimed
authority, digest, or signed JSON is not trusted timestamp verification.
"""
import base64
import hashlib
import json
import re
from pathlib import Path


def inspect_timestamp_attestation(path, *, expected_sha256,
                                  expected_evidence_sha256):
    hold = {"status": "HOLD", "reason": "TRUSTED_TIMESTAMP_NOT_VERIFIED",
            "attestation_integrity": "FAIL",
            "trusted_timestamp_authority_verified": False,
            "production_recommendations": "DISABLED"}
    if (not isinstance(path, (str, Path))
            or not isinstance(expected_sha256, str)
            or not isinstance(expected_evidence_sha256, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256) is None
            or re.fullmatch(r"[0-9a-fA-F]{64}", expected_evidence_sha256) is None):
        return hold
    try:
        source = Path(path)
        if source.stat().st_size > 100_000:
            return hold
        with source.open("rb") as stream:
            raw = stream.read(100_001)
        if (len(raw) > 100_000
                or hashlib.sha256(raw).hexdigest() != expected_sha256.lower()):
            return hold
        def reject_duplicates(pairs):
            obj = {}
            for key, value in pairs:
                if key in obj:
                    raise ValueError("duplicate JSON key")
                obj[key] = value
            return obj
        data = json.loads(raw, object_pairs_hook=reject_duplicates,
                          parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
    except (OSError, ValueError, TypeError, RecursionError, UnicodeDecodeError):
        return hold
    if (not isinstance(data, dict)
            or set(data) != {"schema_version", "format", "timestamp_token_b64",
                                "evidence_sha256"}
            or type(data["schema_version"]) is not int
            or data["schema_version"] != 1
            or data["format"] != "RFC3161_DER"
            or data["evidence_sha256"] != expected_evidence_sha256.lower()
            or not isinstance(data["timestamp_token_b64"], str)):
        return hold
    try:
        token = base64.b64decode(data["timestamp_token_b64"], validate=True)
    except (ValueError, base64.binascii.Error):
        return hold
    if not 32 <= len(token) <= 65_536:
        return hold
    return {"status": "RESEARCH_ONLY",
            "reason": "TIMESTAMP_TOKEN_PRESENT_NOT_CRYPTOGRAPHICALLY_VERIFIED",
            "attestation_integrity": "PASS",
            "token_sha256": hashlib.sha256(token).hexdigest(),
            "trusted_timestamp_authority_verified": False,
            "production_recommendations": "DISABLED"}
