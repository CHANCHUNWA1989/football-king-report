"""Fail-closed offline key lifecycle checks for research receipt verification.

Registry is a separately pinned research input, not evidence of issuer identity.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone

def _utc(value: str) -> datetime:
    if type(value) is not str:
        raise ValueError("timestamp required")
    try:
        d=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if d.tzinfo is None or d.utcoffset() is None:
        raise ValueError("timezone required")
    return d.astimezone(timezone.utc)

def inspect_key_lifecycle(binding: dict, registry: dict, pinned_registry_sha256: str,
                          verification_time: str) -> dict:
    if type(registry) is not dict or registry.get("schema")!="football-king-trusted-key-registry-v1":
        raise ValueError("invalid key registry")
    if type(pinned_registry_sha256) is not str or len(pinned_registry_sha256)!=64 or any(c not in "0123456789abcdef" for c in pinned_registry_sha256):
        raise ValueError("pinned registry digest required")
    canonical=json.dumps(registry,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    if hashlib.sha256(canonical).hexdigest()!=pinned_registry_sha256:
        raise ValueError("registry digest pin mismatch")
    now=_utc(verification_time)
    entries=registry.get("keys")
    if type(entries) is not list or not entries:
        raise ValueError("empty key registry")
    if type(binding) is not dict:
        raise ValueError("binding required")
    ids=set()
    selected=None
    for entry in entries:
        if type(entry) is not dict or any(type(entry.get(k)) is not str for k in ("issuer","key_id","public_key_sha256","not_before","not_after","state")):
            raise ValueError("malformed key entry")
        identity=(entry["issuer"],entry["key_id"])
        if identity in ids:
            raise ValueError("duplicate key identity")
        ids.add(identity)
        start,end=_utc(entry["not_before"]),_utc(entry["not_after"])
        if start>=end:
            raise ValueError("invalid key validity window")
        if identity==(binding.get("issuer"),binding.get("key_id")):
            selected=entry
    if selected is None or selected["public_key_sha256"]!=binding.get("public_key_sha256"):
        raise ValueError("key missing or digest mismatch")
    if selected["state"]!="active":
        raise ValueError("key revoked or inactive")
    if not (_utc(selected["not_before"])<=now<_utc(selected["not_after"])):
        raise ValueError("key outside validity window")
    return {"key_lifecycle_checked":True,"registry_digest_pin_matched":True,
            "key_active_at_verification_time":True,
            "issuer_independence_authenticated":False,
            "trusted_timestamp_verified":False,
            "authenticated_samples":0,"status":"HOLD",
            "model_promotion_allowed":False,"production_recommendations":"DISABLED"}
