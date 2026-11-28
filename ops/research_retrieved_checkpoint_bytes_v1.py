"""Offline comparison of separately retrieved checkpoint bytes (research only).

The caller must retrieve bytes independently. This module cannot authenticate
network transport, publication time, publisher identity, or independence.
"""
from __future__ import annotations
import hashlib
import json
from ops.research_external_checkpoint_claim_v1 import inspect_external_checkpoint

def _reject_duplicate_keys(pairs):
    obj={}
    for key,value in pairs:
        if key in obj:
            raise ValueError("duplicate checkpoint JSON key")
        obj[key]=value
    return obj

def _reject_nonfinite_constant(value):
    raise ValueError("non-finite JSON constant rejected")

def inspect_retrieved_checkpoint(inventory:dict, checkpoint:dict,
                                 pinned_checkpoint_sha256:str,
                                 retrieved_bytes:bytes,
                                 expected_retrieval_sha256:str)->dict:
    claim=inspect_external_checkpoint(inventory,checkpoint,pinned_checkpoint_sha256)
    if type(retrieved_bytes) is not bytes or not retrieved_bytes:
        raise ValueError("nonempty retrieved checkpoint bytes required")
    if (type(expected_retrieval_sha256) is not str
            or len(expected_retrieval_sha256)!=64
            or any(c not in "0123456789abcdef" for c in expected_retrieval_sha256)
            or hashlib.sha256(retrieved_bytes).hexdigest()!=expected_retrieval_sha256):
        raise ValueError("retrieved bytes digest mismatch")
    if retrieved_bytes.startswith((b"\\xef\\xbb\\xbf",b"\\xff\\xfe",b"\\xfe\\xff")):
        raise ValueError("checkpoint byte-order mark rejected")
    try:
        parsed=json.loads(retrieved_bytes.decode("utf-8"),
                          object_pairs_hook=_reject_duplicate_keys,
                          parse_constant=_reject_nonfinite_constant)
    except (UnicodeDecodeError,json.JSONDecodeError) as exc:
        raise ValueError("retrieved checkpoint is not valid UTF-8 JSON") from exc
    if type(parsed) is not dict or set(parsed)!={"schema","inventory_sha256","publisher","locator","published_at"}:
        raise ValueError("checkpoint JSON must contain exactly the expected fields")
    if type(parsed) is not dict or parsed!=checkpoint:
        raise ValueError("retrieved checkpoint differs from pinned claim")
    return {**claim,"retrieved_bytes_digest_matched":True,
            "retrieved_content_matches_claim":True,
            "checkpoint_externally_retrieved":False,
            "retrieval_origin_authenticated":False,
            "publisher_identity_authenticated":False,
            "publisher_independence_authenticated":False,
            "trusted_timestamp_verified":False,
            "authenticated_samples":0,"status":"HOLD",
            "model_promotion_allowed":False,"production_recommendations":"DISABLED"}
