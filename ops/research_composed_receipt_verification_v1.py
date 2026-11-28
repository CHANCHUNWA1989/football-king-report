"""Research-only composed receipt verification. Every prerequisite is mandatory.

Passing checks proves offline integrity under supplied pins, not issuer authenticity,
trusted timestamp, independence, or eligibility for production promotion.
"""
from __future__ import annotations
from ops.research_receipt_signature_ed25519_v1 import verify_receipt_ed25519
from ops.research_trusted_key_lifecycle_v1 import inspect_key_lifecycle

def inspect_composed_receipt(candidate:dict, artifact:bytes, receipt_bytes:bytes,
                             trust_policy:dict, signature_b64:str,
                             trusted_public_key_b64:str, trusted_key_binding:dict,
                             pinned_binding_sha256:str, key_registry:dict,
                             pinned_registry_sha256:str, verification_time:str)->dict:
    signature=verify_receipt_ed25519(
        candidate,artifact,receipt_bytes,trust_policy,signature_b64,
        trusted_public_key_b64,trusted_key_binding,pinned_binding_sha256)
    lifecycle=inspect_key_lifecycle(
        trusted_key_binding,key_registry,pinned_registry_sha256,verification_time)
    if not (signature.get("signature_cryptographically_verified")
            and signature.get("binding_digest_pin_matched")
            and lifecycle.get("key_lifecycle_checked")
            and lifecycle.get("registry_digest_pin_matched")):
        raise ValueError("incomplete receipt verification")
    return {**signature,
            "key_lifecycle_checked":True,
            "registry_digest_pin_matched":True,
            "offline_receipt_checks_passed":True,
            "trusted_timestamp_verified":False,
            "issuer_independence_authenticated":False,
            "authenticated_samples":0,
            "status":"HOLD",
            "model_promotion_allowed":False,
            "production_recommendations":"DISABLED"}
