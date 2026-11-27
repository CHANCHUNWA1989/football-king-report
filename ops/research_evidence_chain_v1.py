"""Research-only append-only hash-chain for evidence bundles.

An in-memory chain is not external notarization. Persist and independently
anchor the terminal hash before relying on it for audit.
"""
from __future__ import annotations
import hashlib
import json
from typing import Sequence
from ops.research_evidence_ledger_v1 import verify_record

GENESIS="0"*64

def _digest(obj: dict) -> str:
    return hashlib.sha256(json.dumps(obj,sort_keys=True,
        separators=(",",":"),allow_nan=False).encode("utf-8")).hexdigest()

def append_evidence(chain: Sequence[dict], forecast: dict) -> dict:
    if not verify_record(forecast):
        raise ValueError("invalid forecast evidence")
    if not verify_chain(chain):
        raise ValueError("existing chain corrupted")
    if any(x["event_id"]==forecast["event_id"] for x in chain):
        raise ValueError("duplicate event id")
    entry={"sequence":len(chain),"event_id":forecast["event_id"],
           "forecast_sha256":forecast["sha256"],
           "previous_sha256":chain[-1]["entry_sha256"] if chain else GENESIS,
           "status":"RESEARCH_ONLY"}
    entry["entry_sha256"]=_digest(entry)
    return entry

def verify_chain(chain: Sequence[dict]) -> bool:
    previous=GENESIS
    events=set()
    for index,entry in enumerate(chain):
        if not isinstance(entry,dict) or entry.get("sequence")!=index or (
            entry.get("previous_sha256")!=previous) or entry.get("event_id") in events:
            return False
        body={k:v for k,v in entry.items() if k!="entry_sha256"}
        try:
            if _digest(body)!=entry.get("entry_sha256"):
                return False
        except (ValueError,TypeError):
            return False
        events.add(entry["event_id"])
        previous=entry["entry_sha256"]
    return True

def chain_audit(chain: Sequence[dict]) -> dict:
    valid=verify_chain(chain)
    return {"status":"RESEARCH_ONLY" if valid else "HOLD",
            "entries":len(chain),"chain_valid":valid,
            "terminal_sha256":chain[-1]["entry_sha256"] if valid and chain else GENESIS,
            "external_anchor_verified":False,
            "production_recommendations":"DISABLED",
            "qualified_for_production":False}
