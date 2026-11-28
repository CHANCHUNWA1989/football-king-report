"""Offline Ed25519 receipt signature verification using explicitly trusted public key.

Signature validity is not timestamp authentication, issuer independence, or OOS proof.
Trust anchors must be supplied out-of-band, never taken from the receipt itself.
"""
from __future__ import annotations
import base64
import binascii
import hashlib
from ops.research_receipt_trust_prerequisites_v1 import inspect_receipt_trust_prerequisites

def verify_receipt_ed25519(candidate:dict, artifact:bytes, receipt_bytes:bytes,
                           trust_policy:dict, signature_b64:str,
                           trusted_public_key_b64:str,
                           trusted_key_binding:dict|None=None)->dict:
    base=inspect_receipt_trust_prerequisites(candidate,artifact,receipt_bytes,trust_policy)
    if type(signature_b64) is not str or type(trusted_public_key_b64) is not str:
        raise ValueError("signature and trusted key required")
    try:
        signature=base64.b64decode(signature_b64,validate=True)
        public_key=base64.b64decode(trusted_public_key_b64,validate=True)
    except (ValueError,binascii.Error) as exc:
        raise ValueError("invalid signature or key encoding") from exc
    if type(trusted_key_binding) is not dict:
        raise ValueError("out-of-band key binding required")
    if (trusted_key_binding.get("schema")!="football-king-trusted-key-binding-v1"
            or trusted_key_binding.get("issuer")!=trust_policy["issuer"]
            or trusted_key_binding.get("key_id")!=trust_policy["key_id"]
            or trusted_key_binding.get("public_key_sha256")!=hashlib.sha256(public_key).hexdigest()):
        raise ValueError("trusted key binding mismatch")
    if len(signature)!=64 or len(public_key)!=32:
        raise ValueError("invalid Ed25519 signature or public key length")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except ImportError as exc:
        raise RuntimeError("cryptography package required for signature verification") from exc
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature,receipt_bytes)
    except (InvalidSignature,ValueError) as exc:
        raise ValueError("receipt signature verification failed") from exc
    return {**base,
            "signature_cryptographically_verified":True,
            "trusted_key_supplied_out_of_band":True,
            "key_binding_claim_checked":True,
            "certificate_chain_verified":False,
            "trusted_timestamp_verified":False,
            "issuer_independence_authenticated":False,
            "authenticated_samples":0,
            "status":"HOLD","model_promotion_allowed":False,
            "production_recommendations":"DISABLED"}
