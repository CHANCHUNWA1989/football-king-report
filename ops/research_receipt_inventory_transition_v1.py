"""Fail-closed append-only inventory transition validation (research only).

Both snapshots must be pinned out of band. A valid transition does not prove
that either snapshot is complete or independently witnessed.
"""
import hashlib
import json

def _digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def inspect_inventory_transition(previous:dict, previous_pin:str,
                                 current:dict, current_pin:str)->dict:
    for snapshot,pin in ((previous,previous_pin),(current,current_pin)):
        if type(snapshot) is not dict or snapshot.get("schema")!="football-king-receipt-replay-inventory-v1":
            raise ValueError("invalid inventory snapshot")
        if type(pin) is not str or len(pin)!=64 or any(c not in "0123456789abcdef" for c in pin) or _digest(snapshot)!=pin:
            raise ValueError("snapshot pin mismatch")
        entries=snapshot.get("entries")
        if type(entries) is not list:
            raise ValueError("inventory entries required")
        fixtures=set()
        receipts=set()
        for item in entries:
            if type(item) is not dict or set(item)!={"fixture_key","receipt_sha256"}:
                raise ValueError("invalid inventory entry")
            fixture,digest=item["fixture_key"],item["receipt_sha256"]
            if type(fixture) is not str or not fixture or type(digest) is not str or len(digest)!=64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("invalid inventory entry value")
            if fixture in fixtures or digest in receipts:
                raise ValueError("duplicate fixture or receipt")
            fixtures.add(fixture)
            receipts.add(digest)
    old=previous["entries"]
    new=current["entries"]
    if len(new)<len(old) or new[:len(old)]!=old:
        raise ValueError("inventory rollback, rewrite, or reordering")
    return {"append_only_transition_checked":True,
            "previous_and_current_pins_matched":True,
            "new_entries":len(new)-len(old),
            "external_checkpoint_authenticated":False,
            "authenticated_samples":0,"status":"HOLD",
            "model_promotion_allowed":False,"production_recommendations":"DISABLED"}
