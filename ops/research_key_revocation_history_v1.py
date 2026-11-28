"""Research-only pinned key revocation history check.

Evaluates revocation at verification time, not purported signing time.
No timestamp or issuer authentication is inferred from supplied metadata.
"""
from __future__ import annotations
import hashlib
import json
from ops.research_trusted_key_lifecycle_v1 import _utc

def inspect_revocation_history(binding:dict, history:dict, pinned_history_sha256:str,
                               verification_time:str)->dict:
    if type(binding) is not dict or type(history) is not dict or history.get("schema")!="football-king-key-revocation-history-v1":
        raise ValueError("invalid revocation history")
    if type(pinned_history_sha256) is not str or len(pinned_history_sha256)!=64 or any(c not in "0123456789abcdef" for c in pinned_history_sha256):
        raise ValueError("revocation history pin required")
    canonical=json.dumps(history,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    if hashlib.sha256(canonical).hexdigest()!=pinned_history_sha256:
        raise ValueError("revocation history pin mismatch")
    when=_utc(verification_time)
    entries=history.get("events")
    if type(entries) is not list:
        raise ValueError("revocation events required")
    seen=set()
    relevant=[]
    for event in entries:
        if type(event) is not dict or any(type(event.get(k)) is not str for k in ("issuer","key_id","revoked_at","reason")):
            raise ValueError("invalid revocation event")
        identity=(event["issuer"],event["key_id"])
        if identity in seen:
            raise ValueError("duplicate revocation event")
        seen.add(identity)
        timestamp=_utc(event["revoked_at"])
        if identity==(binding.get("issuer"),binding.get("key_id")):
            relevant.append(timestamp)
    if any(t<=when for t in relevant):
        raise ValueError("key revoked at verification time")
    return {"revocation_history_pin_matched":True,
            "not_revoked_at_verification_time":True,
            "revocation_history_source_authenticated":False,
            "trusted_timestamp_verified":False,
            "authenticated_samples":0,"status":"HOLD",
            "model_promotion_allowed":False,"production_recommendations":"DISABLED"}
