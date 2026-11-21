"""Explicit Ed25519 trust-anchor allowlist with bounded validity and revocation.

Trust policy must be provisioned out-of-band; this module cannot authenticate
who controls a key or whether a timestamp is issued by an independent clock.
"""
import base64
from datetime import datetime, timezone
from ops.private_signed_timestamp import verify_signed


def _utc(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_POLICY_TIME")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_POLICY_TIME") from exc
    if stamp.tzinfo is None:
        raise ValueError("NAIVE_POLICY_TIME")
    return stamp.astimezone(timezone.utc)


def verify_with_policy(snapshot, signed, policy, *, verification_time_utc):
    if not isinstance(policy, dict) or set(policy) != {"schema", "anchors"} or policy["schema"] != "research-trust-policy-v1":
        raise ValueError("INVALID_TRUST_POLICY")
    anchors = policy["anchors"]
    if not isinstance(anchors, list) or not anchors:
        raise ValueError("EMPTY_TRUST_POLICY")
    if not isinstance(signed, dict) or not isinstance(signed.get("receipt"), dict):
        raise ValueError("INVALID_SIGNED_RECEIPT")
    authority = signed["receipt"].get("authority")
    now = _utc(verification_time_utc)
    matched = []
    seen = set()
    for anchor in anchors:
        if not isinstance(anchor, dict) or set(anchor) != {"authority", "public_key_b64", "valid_from_utc", "valid_until_utc", "revoked"}:
            raise ValueError("INVALID_TRUST_ANCHOR")
        name, key = anchor["authority"], anchor["public_key_b64"]
        if not isinstance(name, str) or not name or not isinstance(key, str) or (name, key) in seen or type(anchor["revoked"]) is not bool:
            raise ValueError("INVALID_TRUST_ANCHOR")
        seen.add((name, key))
        try:
            decoded = base64.b64decode(key, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("INVALID_TRUST_KEY") from exc
        if len(decoded) != 32:
            raise ValueError("INVALID_TRUST_KEY")
        start, end = _utc(anchor["valid_from_utc"]), _utc(anchor["valid_until_utc"])
        if start >= end:
            raise ValueError("INVALID_TRUST_WINDOW")
        if name == authority and not anchor["revoked"] and start <= now < end:
            matched.append(key)
    if len(matched) != 1:
        raise ValueError("NO_UNIQUE_ACTIVE_TRUST_ANCHOR")
    result = verify_signed(snapshot, signed, trusted_public_key_b64=matched[0])
    return {**result, "trust_anchor_allowlisted": True,
            "trust_anchor_active_at_verification": True,
            "authority_identity_independently_verified": False,
            "capture_time_independently_attested": False,
            "production_recommendations": "DISABLED"}
