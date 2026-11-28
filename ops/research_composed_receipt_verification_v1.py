"""Research-only composed receipt verification. Every prerequisite is mandatory.

Passing checks proves offline integrity under supplied pins, not issuer authenticity,
trusted timestamp, independence, or eligibility for production promotion.
"""
from __future__ import annotations
from ops.research_receipt_signature_ed25519_v1 import verify_receipt_ed25519
from ops.research_trusted_key_lifecycle_v1 import inspect_key_lifecycle
from ops.research_key_revocation_history_v1 import inspect_revocation_history
from ops.research_receipt_replay_inventory_v1 import inspect_receipt_replay
from ops.research_receipt_inventory_transition_v1 import inspect_inventory_transition

def inspect_composed_receipt(candidate:dict, artifact:bytes, receipt_bytes:bytes,
                             trust_policy:dict, signature_b64:str,
                             trusted_public_key_b64:str, trusted_key_binding:dict,
                             pinned_binding_sha256:str, key_registry:dict,
                             pinned_registry_sha256:str, verification_time:str,
                             revocation_history:dict|None=None,
                             pinned_revocation_history_sha256:str|None=None,
                             replay_inventory:dict|None=None,
                             pinned_replay_inventory_sha256:str|None=None,
                             previous_replay_inventory:dict|None=None,
                             pinned_previous_inventory_sha256:str|None=None)->dict:
    signature=verify_receipt_ed25519(
        candidate,artifact,receipt_bytes,trust_policy,signature_b64,
        trusted_public_key_b64,trusted_key_binding,pinned_binding_sha256)
    lifecycle=inspect_key_lifecycle(
        trusted_key_binding,key_registry,pinned_registry_sha256,verification_time)
    revocation=inspect_revocation_history(
        trusted_key_binding,revocation_history,pinned_revocation_history_sha256,verification_time)
    replay=inspect_receipt_replay(candidate.get("fixture_key"),receipt_bytes,
                                  replay_inventory,pinned_replay_inventory_sha256)
    transition=inspect_inventory_transition(
        previous_replay_inventory,pinned_previous_inventory_sha256,
        replay_inventory,pinned_replay_inventory_sha256)
    if not transition.get("append_only_transition_checked"):
        raise ValueError("inventory transition check incomplete")
    if not replay.get("receipt_replay_inventory_checked"):
        raise ValueError("receipt replay check incomplete")
    if not revocation.get("not_revoked_at_verification_time"):
        raise ValueError("revocation check incomplete")
    if not (signature.get("signature_cryptographically_verified")
            and signature.get("binding_digest_pin_matched")
            and lifecycle.get("key_lifecycle_checked")
            and lifecycle.get("registry_digest_pin_matched")):
        raise ValueError("incomplete receipt verification")
    return {**signature,
            "append_only_transition_checked":True,
            "external_checkpoint_authenticated":False,
            "receipt_replay_inventory_checked":True,
            "inventory_digest_pin_matched":True,
            "revocation_history_pin_matched":True,
            "not_revoked_at_verification_time":True,
            "key_lifecycle_checked":True,
            "registry_digest_pin_matched":True,
            "offline_receipt_checks_passed":True,
            "trusted_timestamp_verified":False,
            "issuer_independence_authenticated":False,
            "authenticated_samples":0,
            "status":"HOLD",
            "model_promotion_allowed":False,
            "production_recommendations":"DISABLED"}
