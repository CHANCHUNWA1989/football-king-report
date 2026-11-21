"""Verify Ed25519 signatures on canonical private forecast timestamp receipts.

Trust anchor is supplied out-of-band. Signature does not authenticate clock.
Optional dependency: cryptography. No private keys are handled here.
"""
import base64
import json
from ops.private_timestamp_receipt import check


def verify_signed(snapshot, signed, *, trusted_public_key_b64):
    if not isinstance(signed, dict) or set(signed) != {"receipt", "signature_b64", "algorithm"} or signed["algorithm"] != "Ed25519":
        raise ValueError("INVALID_SIGNED_RECEIPT")
    receipt = signed["receipt"]
    # Enforce receipt schema, digest binding and prematch chronology first.
    result = check(snapshot, receipt)
    if not isinstance(trusted_public_key_b64, str) or not isinstance(signed["signature_b64"], str):
        raise ValueError("INVALID_KEY_OR_SIGNATURE")
    try:
        public_key = base64.b64decode(trusted_public_key_b64, validate=True)
        signature = base64.b64decode(signed["signature_b64"], validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("INVALID_SIGNATURE_ENCODING") from exc
    if len(public_key) != 32 or len(signature) != 64:
        raise ValueError("INVALID_KEY_OR_SIGNATURE_LENGTH")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except ImportError as exc:
        raise ValueError("CRYPTOGRAPHY_DEPENDENCY_UNAVAILABLE") from exc
    message = json.dumps(receipt, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, message)
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("INVALID_RECEIPT_SIGNATURE") from exc
    return {**result, "signature_valid": True, "trusted_public_key_matched": True,
            "independent_authority_authenticated": False,
            "capture_time_independently_attested": False,
            "production_recommendations": "DISABLED",
            "positive_ev_verified": False}
