"""Offline prospective evidence audit: identity overlap and hash-chain integrity.

Caller must independently authenticate canonical fixture IDs, registry completeness,
publication timestamps and the external chain anchor. This module does not publish.
"""
from collections.abc import Mapping
from datetime import timezone
from hashlib import sha256
from json import dumps
from math import fsum,isfinite
from ops.live_snapshot_market_audit_20261126 import aware

GENESIS="0"*64

def identifier(v):
    if not isinstance(v,str) or not v or v.strip()!=v or len(v)>256:
        raise ValueError("invalid identifier")
    return v

def utc(v):
    return aware(v).astimezone(timezone.utc).isoformat()

def digest(v):
    return sha256(dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

def identities(ids,aliases):
    if not isinstance(ids,(list,tuple)) or not isinstance(aliases,Mapping):
        raise ValueError("invalid registry")
    out=[]
    for v in ids:
        v=identifier(v)
        if v not in aliases: raise ValueError("unmapped fixture")
        out.append(identifier(aliases[v]))
    if len(set(out))!=len(out): raise ValueError("duplicate canonical fixture")
    return set(out)

def overlap(candidate, prior, aliases):
    current=identities(candidate,aliases)
    if not current or not isinstance(prior,Mapping):
        raise ValueError("invalid cohort")
    found={}
    for key,ids in prior.items():
        key=identifier(key)
        intersect=current & identities(ids,aliases)
        if intersect: found[key]=sorted(intersect)
    return {"canonical_count":len(current),"cohort_sha256":digest(sorted(current)),
            "overlaps":found,"overlap_count":len({v for vs in found.values() for v in vs}),
            "status":"HOLD" if found else "NO_KNOWN_OVERLAP",
            "registry_completeness_verified":False,"promotion_authorized":False}

def _prob(v):
    if not isinstance(v,(list,tuple)) or len(v)!=3 or any(type(x) not in (int,float) or not isfinite(x) or not 0<=x<=1 for x in v) or abs(fsum(v)-1)>1e-9:
        raise ValueError("invalid probability")
    return list(v)

def canonical_manifest(manifest,aliases):
    if not isinstance(manifest,Mapping): raise ValueError("invalid manifest")
    frozen=utc(manifest["frozen_at"])
    baseline=identifier(manifest["baseline_id"])
    challenger=identifier(manifest["challenger_id"])
    if baseline==challenger: raise ValueError("identical models")
    rows=manifest["fixtures"]
    if not isinstance(rows,list) or not rows: raise ValueError("empty cohort")
    identities([r["fixture_id"] for r in rows],aliases)
    fixtures={aliases[r["fixture_id"]]:utc(r["decision_at"]) for r in rows}
    if any(aware(t)<=aware(frozen) for t in fixtures.values()):
        raise ValueError("decision before freeze")
    return {"frozen_at":frozen,"baseline_id":baseline,"challenger_id":challenger,
            "fixtures":fixtures}

def seal(entry,previous):
    if not isinstance(previous,str) or len(previous)!=64 or any(c not in "0123456789abcdef" for c in previous):
        raise ValueError("invalid predecessor")
    return {"entry":entry,"previous":previous,"sha256":digest({"entry":entry,"previous":previous})}

def audit(manifest,records,aliases,prior,expected_head):
    m=canonical_manifest(manifest,aliases)
    md=digest(m)
    o=overlap([r["fixture_id"] for r in manifest["fixtures"]],prior,aliases)
    if not isinstance(records,list): raise ValueError("invalid archive")
    previous=GENESIS;seen=set();last=None
    for record in records:
        if not isinstance(record,Mapping) or set(record)!={"entry","previous","sha256"}:
            raise ValueError("invalid record")
        e=record["entry"]
        if not isinstance(e,Mapping) or set(e)!={"fixture_id","model_id","manifest_sha256","issued_at","features_through","trained_through","probabilities"}:
            raise ValueError("invalid forecast schema")
        if record!=seal(e,previous): raise ValueError("broken hash chain")
        previous=record["sha256"]
        fid=identifier(e["fixture_id"]);model=identifier(e["model_id"])
        if fid not in aliases or aliases[fid] not in m["fixtures"] or model not in (m["baseline_id"],m["challenger_id"]) or e["manifest_sha256"]!=md:
            raise ValueError("unregistered forecast")
        canonical=aliases[fid];key=(canonical,model)
        if key in seen: raise ValueError("duplicate forecast")
        seen.add(key)
        issue=aware(e["issued_at"]);cutoff=aware(m["fixtures"][canonical]);freeze=aware(m["frozen_at"])
        if not aware(e["trained_through"])<=freeze<=issue<=cutoff or not aware(e["features_through"])<=issue:
            raise ValueError("forecast chronology violation")
        if last is not None and issue<last: raise ValueError("nonmonotone archive")
        last=issue
        _prob(e["probabilities"])
    expected={(f,k) for f in m["fixtures"] for k in (m["baseline_id"],m["challenger_id"])}
    reasons=[]
    if seen!=expected: reasons.append("INCOMPLETE_PAIRED_ARCHIVE")
    if previous!=expected_head: reasons.append("ANCHOR_MISMATCH")
    if o["overlap_count"]: reasons.append("KNOWN_COHORT_OVERLAP")
    return {"status":"HOLD" if reasons else "STRUCTURAL_REVIEW_REQUIRED",
            "reasons":reasons,"manifest_sha256":md,"archive_head":previous,
            "expected_forecasts":len(expected),"observed_forecasts":len(seen),"overlap":o,
            "external_anchor_authenticated":False,"source_attestation_verified":False,
            "prospective_verified":False,"promotion_authorized":False,
            "deployment":"HOLD","recommendations":"DISABLED","positive_ev_verified":False}
