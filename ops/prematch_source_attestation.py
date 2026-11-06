"""Optional independent source signature and trusted timestamp boundary.

No signing key, trusted TSA, or live provider is bundled.
"""
import base64
import hashlib
from datetime import datetime, timezone


def verify_attestation(raw, *, signature_b64, public_key_pem,
                       timestamp_utc, trusted_time_utc,
                       max_skew_seconds=120):
    """Verify Ed25519 over exact raw response and bounded independent time.

    trusted_time_utc MUST be obtained from a separately trusted clock or TSA
    verification layer; caller-supplied timestamps alone are not trustworthy.
    """
    hold = {"status": "HOLD", "signature_verified": False,
            "trusted_timestamp_verified": False,
            "production_recommendations": "DISABLED"}
    if not isinstance(raw, bytes) or not raw or len(raw) > 1_000_000:
        return {**hold, "reason": "INVALID_SIGNED_PAYLOAD"}
    if not isinstance(public_key_pem, bytes) or not isinstance(signature_b64, str):
        return {**hold, "reason": "MISSING_SIGNATURE_EVIDENCE"}
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        key = serialization.load_pem_public_key(public_key_pem)
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("wrong key algorithm")
        signature = base64.b64decode(signature_b64, validate=True)
        key.verify(signature, raw)
    except (ValueError, TypeError, ImportError, Exception) as exc:
        return {**hold, "reason": "SIGNATURE_VERIFICATION_FAILED"}
    def parse(value):
        if not isinstance(value, str):
            raise ValueError("missing timestamp")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("naive timestamp")
        return parsed.astimezone(timezone.utc)
    try:
        captured = parse(timestamp_utc)
        trusted = parse(trusted_time_utc)
        if (type(max_skew_seconds) is not int or not 0 <= max_skew_seconds <= 300
                or abs((trusted - captured).total_seconds()) > max_skew_seconds):
            raise ValueError("timestamp mismatch")
    except (ValueError, TypeError):
        return {**hold, "reason": "TIMESTAMP_EVIDENCE_INVALID",
                "signature_verified": True}
    return {"status": "RESEARCH_ONLY", "reason": "INDEPENDENT_TSA_NOT_ATTESTED",
            "signature_verified": True,
            "trusted_timestamp_verified": False,
            "response_sha256": hashlib.sha256(raw).hexdigest(),
            "production_recommendations": "DISABLED"}
