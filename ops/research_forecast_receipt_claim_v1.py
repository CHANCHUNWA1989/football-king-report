"""Offline receipt-to-artifact digest consistency; no cryptographic trust assertion.

This parser only checks a caller-supplied JSON receipt. It cannot verify a
signature, independent issuer, trusted timestamp, or actual network provenance.
"""
from __future__ import annotations
import hashlib
import json
from ops.research_forecast_artifact_integrity_v1 import inspect_forecast_artifact

MAX_RECEIPT_BYTES=100_000

def _unique_pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            raise ValueError("duplicate receipt JSON field")
        result[key]=value
    return result

def inspect_receipt_claim(candidate:dict, artifact:bytes, receipt_bytes:bytes)->dict:
    integrity=inspect_forecast_artifact(candidate,artifact)
    if type(receipt_bytes) is not bytes or not receipt_bytes or len(receipt_bytes)>MAX_RECEIPT_BYTES:
        raise ValueError("invalid receipt bytes")
    def reject_constant(value):
        raise ValueError("nonfinite receipt value")
    receipt=json.loads(receipt_bytes.decode("utf-8"),object_pairs_hook=_unique_pairs,
                       parse_constant=reject_constant)
    if type(receipt) is not dict:
        raise ValueError("receipt must be object")
    if (receipt.get("schema")!="football-king-archive-receipt-claim-v1"
            or receipt.get("fixture_key")!=candidate["fixture_key"]
            or receipt.get("artifact_sha256")!=integrity["forecast_sha256"]):
        raise ValueError("receipt artifact identity mismatch")
    return {"schema":"forecast-receipt-claim-check-v1",
            "fixture_key":integrity["fixture_key"],
            "artifact_integrity_verified":True,
            "receipt_claim_digest_matches":True,
            "receipt_signature_verified":False,
            "trusted_timestamp_verified":False,
            "third_party_issuer_authenticated":False,
            "authenticated_samples":0,
            "status":"HOLD","model_promotion_allowed":False,
            "production_recommendations":"DISABLED"}
