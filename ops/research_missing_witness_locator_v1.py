"""Locate missing fixture witness IDs from real archive inventories.

Inputs must be caller-supplied verified inventories, not fabricated summaries.
This is diagnostic only and never authenticates a fixture or enables production.
"""
from __future__ import annotations
import hashlib
import json

def _ids(rows:list[dict],name:str)->set[str]:
    if type(rows) is not list:
        raise ValueError(name+" must be list")
    result=set()
    for row in rows:
        if type(row) is not dict or set(row)!={"fixture_id"}:
            raise ValueError(name+" requires fixture_id only")
        fid=row["fixture_id"]
        if type(fid) is not str or not fid.strip() or fid!=fid.strip() or len(fid)>256:
            raise ValueError("invalid fixture_id")
        if fid in result:
            raise ValueError("duplicate fixture_id")
        result.add(fid)
    return result

def locate_missing_witnesses(*,candidates:list[dict],
                             verified_witnesses:list[dict],
                             expected_ledger_sha256:str|None=None)->dict:
    candidate_ids=_ids(candidates,"candidates")
    witness_ids=_ids(verified_witnesses,"verified_witnesses")
    if not witness_ids.issubset(candidate_ids):
        raise ValueError("witness without matching candidate")
    if expected_ledger_sha256 is not None and (
        type(expected_ledger_sha256) is not str
        or len(expected_ledger_sha256)!=64
        or any(c not in "0123456789abcdef" for c in expected_ledger_sha256)):
        raise ValueError("invalid ledger digest")
    payload={"candidate_ids":sorted(candidate_ids),
             "witness_ids":sorted(witness_ids)}
    digest=hashlib.sha256(json.dumps(
        payload,sort_keys=True,separators=(",",":"),ensure_ascii=False
    ).encode()).hexdigest()
    return {"schema":"football-king-missing-witness-inventory-v1",
            "status":"HOLD","production_recommendations":"DISABLED",
            "model_promotion_allowed":False,"evidence_authenticated":False,
            "candidate_count":len(candidate_ids),
            "witness_count":len(witness_ids),
            "missing_fixture_ids":sorted(candidate_ids-witness_ids),
            "inventory_sha256":digest,
            "ledger_sha256_reference":expected_ledger_sha256,
            "note":"Inventory IDs are caller-supplied; not independently authenticated."}
