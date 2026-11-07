"""Historical key-rotation diagnostics, never independent timestamp attestation.

Signed receipt timestamps are signer assertions, not trusted signing times.
Historical verification requires an externally authenticated time proof.
"""
from ops.private_timestamp_trust_policy import _utc
from ops.private_signed_timestamp import verify_signed


def verify_historical(snapshot, signed, policy, *, verification_time_utc,
                      externally_authenticated_signing_time_utc=None):
    if not isinstance(policy, dict) or set(policy) != {"schema", "anchors"} or policy["schema"] != "research-trust-policy-v1":
        raise ValueError("INVALID_TRUST_POLICY")
    if not isinstance(signed, dict) or not isinstance(signed.get("receipt"), dict):
        raise ValueError("INVALID_SIGNED_RECEIPT")
    if externally_authenticated_signing_time_utc is not None:
        # No independent authentication mechanism is implemented here.
        # Reject caller-provided claims rather than silently trusting them.
        raise ValueError("EXTERNAL_TIME_AUTHENTICATION_NOT_IMPLEMENTED")
    now = _utc(verification_time_utc)
    receipt_time = _utc(signed["receipt"].get("timestamp_utc"))
    if receipt_time > now:
        raise ValueError("RECEIPT_FROM_FUTURE")
    anchors = policy["anchors"]
    if not isinstance(anchors, list) or not anchors:
        raise ValueError("EMPTY_TRUST_POLICY")
    candidates = []
    seen = set()
    for anchor in anchors:
        if not isinstance(anchor, dict) or set(anchor) != {"authority", "public_key_b64", "valid_from_utc", "valid_until_utc", "revoked"}:
            raise ValueError("INVALID_TRUST_ANCHOR")
        authority, key = anchor["authority"], anchor["public_key_b64"]
        if not isinstance(authority, str) or not authority or not isinstance(key, str) or type(anchor["revoked"]) is not bool or (authority, key) in seen:
            raise ValueError("INVALID_TRUST_ANCHOR")
        seen.add((authority, key))
        start, end = _utc(anchor["valid_from_utc"]), _utc(anchor["valid_until_utc"])
        if start >= end:
            raise ValueError("INVALID_TRUST_WINDOW")
        if authority == signed["receipt"].get("authority") and start <= receipt_time < end and not anchor["revoked"]:
            candidates.append(key)
    if len(candidates) != 1:
        raise ValueError("NO_UNIQUE_HISTORICAL_KEY")
    result = verify_signed(snapshot, signed, trusted_public_key_b64=candidates[0])
    return {**result, "historical_key_window_matches_claimed_time": True,
            "historical_signing_time_independently_verified": False,
            "historical_key_trust_status": "UNVERIFIED_SIGNING_TIME",
            "capture_time_independently_attested": False,
            "production_recommendations": "DISABLED", "model_promoted": False}
