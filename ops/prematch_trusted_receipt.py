"""Offline verifiable source receipts with pinned Ed25519 public keys.

A successful signature proves possession of a pinned key, not that the provider
or time authority is independently trusted. Never enables production.
"""
import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

def _time(value):
    if not isinstance(value, str):
        raise ValueError("timestamp missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone aware")
    return parsed.astimezone(timezone.utc)

def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()

def verify_receipt(raw, receipt, *, pinned_keys, expected_provider,
                   trusted_clock=None, max_age_seconds=900):
    """Verify a signed digest-bound receipt, with an optional trusted-clock input.

    The caller must independently authenticate pinned_keys and trusted_clock.
    """
    reasons = []
    result = {"status": "HOLD", "signature_verified": False,
              "trusted_timestamp_verified": False,
              "source_independently_trusted": False,
              "production_recommendations": "DISABLED"}
    if not isinstance(raw, bytes) or not raw or len(raw) > 1_000_000:
        reasons.append("INVALID_RAW_PAYLOAD")
    if not isinstance(receipt, dict) or set(receipt) != {
            "provider_id", "key_id", "sha256", "captured_at_utc", "signature_b64"}:
        reasons.append("INVALID_RECEIPT_SCHEMA")
    if reasons:
        return {**result, "rejection_reasons": reasons}
    signed = {k: receipt[k] for k in ("provider_id", "key_id", "sha256", "captured_at_utc")}
    if receipt["provider_id"] != expected_provider:
        reasons.append("PROVIDER_MISMATCH")
    if receipt["sha256"] != hashlib.sha256(raw).hexdigest():
        reasons.append("DIGEST_MISMATCH")
    if not isinstance(pinned_keys, dict) or receipt["key_id"] not in pinned_keys:
        reasons.append("UNTRUSTED_SIGNING_KEY")
    if not reasons:
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            key = serialization.load_pem_public_key(pinned_keys[receipt["key_id"]])
            if not isinstance(key, Ed25519PublicKey):
                raise ValueError("not Ed25519")
            key.verify(base64.b64decode(receipt["signature_b64"], validate=True),
                       _canonical(signed))
            result["signature_verified"] = True
        except Exception:
            reasons.append("SIGNATURE_INVALID")
    if trusted_clock is None:
        reasons.append("INDEPENDENT_TIMESTAMP_UNAVAILABLE")
    else:
        try:
            captured = _time(receipt["captured_at_utc"])
            reference = _time(trusted_clock)
            if type(max_age_seconds) is not int or not 0 <= max_age_seconds <= 3600:
                raise ValueError("invalid age")
            if not 0 <= (reference - captured).total_seconds() <= max_age_seconds:
                raise ValueError("out of bounds")
            # Clock input is caller-provided; no external TSA was verified.
            reasons.append("TIMESTAMP_AUTHORITY_NOT_VERIFIED")
        except (ValueError, TypeError, OverflowError):
            reasons.append("TIMESTAMP_INVALID_OR_STALE")
    if not reasons:
        reasons.append("INDEPENDENT_SOURCE_NOT_ATTESTED")
    return {**result, "rejection_reasons": reasons,
            "receipt_sha256": hashlib.sha256(_canonical(receipt)).hexdigest()}

def replay_receipt(directory, receipt, *, pinned_keys, expected_provider,
                   trusted_clock=None):
    """Replay an exact archived payload and verify its attached receipt."""
    from prematch_raw_archive import replay_response
    digest = receipt.get("sha256") if isinstance(receipt, dict) else None
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        return {"status": "HOLD", "rejection_reasons": ["INVALID_ARCHIVE_DIGEST"],
                "production_recommendations": "DISABLED"}
    try:
        raw = replay_response(Path(directory) / (digest + ".json"),
                              expected_sha256=digest)
    except (OSError, ValueError):
        return {"status": "HOLD", "rejection_reasons": ["ARCHIVE_REPLAY_FAILED"],
                "production_recommendations": "DISABLED"}
    return verify_receipt(raw, receipt, pinned_keys=pinned_keys,
                          expected_provider=expected_provider,
                          trusted_clock=trusted_clock)
