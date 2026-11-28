"""Fail-closed third-party receipt trust prerequisites, research only.

No public key, certificate chain, signature or trusted timestamp is verified here.
Never promote a claimed receipt to authenticated evidence.
"""
from __future__ import annotations
from urllib.parse import urlsplit
from ops.research_forecast_receipt_claim_v1 import inspect_receipt_claim

def inspect_receipt_trust_prerequisites(candidate:dict,artifact:bytes,receipt_bytes:bytes,
                                        trust_policy:dict)->dict:
    checked=inspect_receipt_claim(candidate,artifact,receipt_bytes)
    if type(trust_policy) is not dict:
        raise ValueError("trust policy object required")
    if trust_policy.get("schema")!="football-king-receipt-trust-policy-v1":
        raise ValueError("unsupported trust policy")
    issuer=trust_policy.get("issuer")
    if type(issuer) is not str or not issuer.strip() or len(issuer)>256:
        raise ValueError("issuer required")
    key_id=trust_policy.get("key_id")
    if type(key_id) is not str or not key_id.strip() or len(key_id)>256:
        raise ValueError("key identifier required")
    policy_url=trust_policy.get("policy_url")
    if type(policy_url) is not str or len(policy_url)>2048:
        raise ValueError("trust policy URL required")
    url=urlsplit(policy_url)
    if url.scheme!="https" or not url.hostname or url.username or url.password or url.fragment:
        raise ValueError("valid HTTPS trust policy URL required")
    return {"schema":"receipt-trust-prerequisites-v1",
            "fixture_key":checked["fixture_key"],
            "receipt_claim_digest_matches":True,
            "trust_policy_claim_present":True,
            "issuer_claim_present":True,
            "key_id_claim_present":True,
            "signature_cryptographically_verified":False,
            "certificate_chain_verified":False,
            "trusted_timestamp_verified":False,
            "issuer_independence_authenticated":False,
            "authenticated_samples":0,
            "status":"HOLD","model_promotion_allowed":False,
            "production_recommendations":"DISABLED"}
