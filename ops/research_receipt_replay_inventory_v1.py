"""Research-only receipt replay inventory checks.

Inventory must be independently pinned; this module does not authenticate its
completeness, issuer, capture time, or source independence.
"""
from __future__ import annotations
import hashlib
import json

def inspect_receipt_replay(fixture_key:str, receipt_bytes:bytes,
                           inventory:dict, pinned_inventory_sha256:str)->dict:
    if type(fixture_key) is not str or not fixture_key.strip() or type(receipt_bytes) is not bytes or not receipt_bytes:
        raise ValueError("fixture and raw receipt bytes required")
    if type(inventory) is not dict or inventory.get("schema")!="football-king-receipt-replay-inventory-v1":
        raise ValueError("invalid replay inventory")
    if type(pinned_inventory_sha256) is not str or len(pinned_inventory_sha256)!=64 or any(c not in "0123456789abcdef" for c in pinned_inventory_sha256):
        raise ValueError("pinned inventory digest required")
    canonical=json.dumps(inventory,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    if hashlib.sha256(canonical).hexdigest()!=pinned_inventory_sha256:
        raise ValueError("replay inventory pin mismatch")
    entries=inventory.get("entries")
    if type(entries) is not list:
        raise ValueError("replay entries required")
    seen_fixtures=set()
    seen_receipts=set()
    receipt_hash=hashlib.sha256(receipt_bytes).hexdigest()
    matches=0
    for entry in entries:
        if type(entry) is not dict or set(entry)!={"fixture_key","receipt_sha256"}:
            raise ValueError("malformed replay entry")
        fixture,digest=entry["fixture_key"],entry["receipt_sha256"]
        if type(fixture) is not str or not fixture or type(digest) is not str or len(digest)!=64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("invalid replay entry values")
        if fixture in seen_fixtures or digest in seen_receipts:
            raise ValueError("duplicate fixture or reused receipt in inventory")
        seen_fixtures.add(fixture)
        seen_receipts.add(digest)
        if fixture==fixture_key:
            if digest!=receipt_hash:
                raise ValueError("fixture receipt substitution")
            matches+=1
        elif digest==receipt_hash:
            raise ValueError("receipt reused for different fixture")
    if matches!=1:
        raise ValueError("receipt absent from pinned replay inventory")
    return {"receipt_replay_inventory_checked":True,
            "inventory_digest_pin_matched":True,
            "inventory_completeness_authenticated":False,
            "authenticated_samples":0,"status":"HOLD",
            "model_promotion_allowed":False,"production_recommendations":"DISABLED"}
