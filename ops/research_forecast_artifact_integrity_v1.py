"""Offline forecast artifact integrity check; never authenticates third-party timestamps.

Caller supplies actual artifact bytes. No network fetch, signature trust or model unlock.
"""
from __future__ import annotations
import hashlib
import json
from ops.research_external_evidence_gate_v1 import inspect_external_evidence

MAX_ARTIFACT_BYTES=5_000_000

def inspect_forecast_artifact(candidate:dict, artifact:bytes)->dict:
    inventory=inspect_external_evidence(candidate)
    if type(artifact) is not bytes or not artifact or len(artifact)>MAX_ARTIFACT_BYTES:
        raise ValueError("forecast artifact bytes required within size limit")
    actual=hashlib.sha256(artifact).hexdigest()
    expected=candidate["forecast_sha256"]
    if actual!=expected:
        raise ValueError("actual forecast artifact SHA-256 mismatch")
    return {"schema":"forecast-artifact-integrity-v1",
            "fixture_key":inventory["fixture_key"],
            "forecast_sha256":actual,
            "artifact_bytes_checked":len(artifact),
            "artifact_integrity_verified":True,
            "third_party_receipt_verified":False,
            "immutable_timestamp_authenticated":False,
            "independence_authenticated":False,
            "authenticated_samples":0,
            "status":"HOLD","model_promotion_allowed":False,
            "production_recommendations":"DISABLED"}
