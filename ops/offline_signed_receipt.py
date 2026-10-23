"""Verify Ed25519 source-receipt signatures against an out-of-band trusted key.

The trusted key must be supplied by the operator from an authenticated channel.
A valid signature does not prove pre-match timing or source truth.
"""
import base64
import json
import re

from offline_source_receipt import validate_source_receipt


def _decode_b64(value, size):
    if not isinstance(value, str):
        return None
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, base64.binascii.Error):
        return None
    return raw if len(raw) == size else None


def verify_signed_source_receipt(envelope, *, trusted_key_id,
                                 trusted_public_key_b64,
                                 expected_history_sha256,
                                 expected_manifest_sha256,
                                 expected_model_version):
    hold = {"status": "HOLD", "reason": "UNVERIFIED_RECEIPT_SIGNATURE",
            "signature_verified": False, "issuer_identity_verified": False,
            "trusted_timestamp_authority_verified": False,
            "production_recommendations": "DISABLED"}
    if (not isinstance(envelope, dict)
            or set(envelope) != {"schema_version", "algorithm", "key_id", "receipt", "signature_b64"}
            or envelope.get("schema_version") != 1
            or envelope.get("algorithm") != "Ed25519"
            or not isinstance(trusted_key_id, str)
            or not trusted_key_id.strip()
            or envelope.get("key_id") != trusted_key_id):
        return hold
    public_key = _decode_b64(trusted_public_key_b64, 32)
    signature = _decode_b64(envelope["signature_b64"], 64)
    if public_key is None or signature is None:
        return hold
    receipt = envelope["receipt"]
    consistency = validate_source_receipt(
        receipt, expected_history_sha256=expected_history_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_model_version=expected_model_version)
    if consistency["status"] != "RESEARCH_ONLY":
        return hold
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        message = json.dumps(receipt, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, message)
    except (ImportError, ValueError, TypeError, OverflowError, Exception) as exc:
        # Includes InvalidSignature; fail closed if crypto is not installed.
        return hold
    return {"status": "RESEARCH_ONLY", "reason": "PINNED_ED25519_SIGNATURE_VALID",
            "signature_verified": True, "issuer_identity_verified": False,
            "trusted_timestamp_authority_verified": False,
            "key_id": trusted_key_id,
            "production_recommendations": "DISABLED"}
