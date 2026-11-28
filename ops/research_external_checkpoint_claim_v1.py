"""Research-only externally supplied checkpoint claim validation.

Matching a pinned checkpoint is NOT proof of independent publication, issuer
authentication, trusted timestamp, or checkpoint availability.
"""
from __future__ import annotations
import hashlib
import json
from ops.research_trusted_key_lifecycle_v1 import _utc
from ops.research_checkpoint_locator_policy_v1 import inspect_checkpoint_locator

def inspect_external_checkpoint(inventory:dict, checkpoint:dict,
                                pinned_checkpoint_sha256:str)->dict:
    if type(inventory) is not dict or type(checkpoint) is not dict:
        raise ValueError("inventory and checkpoint required")
    if checkpoint.get("schema")!="football-king-external-checkpoint-claim-v1":
        raise ValueError("invalid checkpoint schema")
    if type(pinned_checkpoint_sha256) is not str or len(pinned_checkpoint_sha256)!=64 or any(c not in "0123456789abcdef" for c in pinned_checkpoint_sha256):
        raise ValueError("checkpoint pin required")
    canonical=json.dumps(checkpoint,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    if hashlib.sha256(canonical).hexdigest()!=pinned_checkpoint_sha256:
        raise ValueError("checkpoint pin mismatch")
    inventory_digest=hashlib.sha256(json.dumps(inventory,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    if checkpoint.get("inventory_sha256")!=inventory_digest:
        raise ValueError("checkpoint inventory digest mismatch")
    if type(checkpoint.get("publisher")) is not str or not checkpoint["publisher"].strip():
        raise ValueError("checkpoint publisher claim required")
    inspect_checkpoint_locator(checkpoint.get("locator"))
    if type(checkpoint.get("published_at")) is not str:
        raise ValueError("checkpoint publication claim required")
    _utc(checkpoint["published_at"])
    return {"checkpoint_claim_digest_matched":True,
            "checkpoint_pin_matched":True,
            "checkpoint_externally_retrieved":False,
            "publisher_identity_authenticated":False,
            "publisher_independence_authenticated":False,
            "trusted_timestamp_verified":False,
            "authenticated_samples":0,"status":"HOLD",
            "model_promotion_allowed":False,"production_recommendations":"DISABLED"}
