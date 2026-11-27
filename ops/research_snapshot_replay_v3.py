"""Offline replay of exact snapshot bytes and local source fingerprints.

A matching replay is not a signed attestation, a trusted clock, or proof
of independent sources. Never promotes research or executes a trade.
"""
import hashlib
import json
import platform
import sys
from pathlib import Path
from .research_unified_snapshot_consensus_v2 import compare_snapshots

MAX_BYTES=256_000
FILES=("research_multimodel_v1.py","research_asian_settlement_v1.py",
       "research_unified_snapshot_audit_v1.py","research_unified_snapshot_consensus_v2.py",
       "research_snapshot_replay_v3.py")
REQUEST_KEYS={"fixture_id","kickoff","as_of","rates","rates_at","snapshots"}

def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)

def _digest(raw):
    return hashlib.sha256(raw).hexdigest()

def _pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key]=value
    return result

def _bad_constant(value):
    raise ValueError("nonfinite JSON constant")

def _decode(raw):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_BYTES:
        raise ValueError("invalid request bytes")
    doc=json.loads(raw.decode("utf-8"),object_pairs_hook=_pairs,parse_constant=_bad_constant)
    if not isinstance(doc,dict) or set(doc)!=REQUEST_KEYS:
        raise ValueError("unexpected request schema")
    _canonical(doc)  # reject overflowed floating-point values
    return doc

def source_manifest():
    root=Path(__file__).resolve().parent
    entries={}
    for name in FILES:
        path=root/name
        if path.is_symlink() or not path.is_file():
            raise ValueError("missing or unsafe source file")
        with path.open("rb") as stream:
            data=stream.read(MAX_BYTES+1)
        if not 0<len(data)<=MAX_BYTES:
            raise ValueError("invalid source size")
        entries[name]=_digest(data)
    return {"files":entries,"implementation":platform.python_implementation(),
            "python_version":list(sys.version_info[:3])}

def _safety():
    return {"schema":"snapshot-replay-v3","status":"HOLD",
            "production_recommendations":"DISABLED","certified_ev":False,
            "authenticated_samples":0,"independent_oos_proven":False,
            "source_authenticity_verified":False,"model_promotion_allowed":False}

def capture(raw):
    """Capture locally supplied raw request, with a reproducible result.
    The caller retains the original bytes privately; no raw data publication.
    """
    doc=_decode(raw)
    before=source_manifest()
    result=compare_snapshots(**doc)
    if not result.get("structural_consensus_passed"):
        raise ValueError("snapshot rejected")
    if source_manifest()!=before:
        raise ValueError("source changed during calculation")
    receipt={**_safety(),"raw_sha256":_digest(raw),"source_manifest":before,
             "result":result}
    receipt["receipt_sha256"]=_digest(_canonical(receipt).encode("utf-8"))
    return receipt

def replay(raw,receipt):
    """Require byte-identical input, current source files and full recomputation.
    A hash recreated by a caller cannot establish original collection time.
    """
    try:
        if not isinstance(receipt,dict):
            raise ValueError("receipt required")
        expected=capture(raw)
        if _canonical(expected)!=_canonical(receipt):
            raise ValueError("receipt mismatch")
        return {**_safety(),"replay_passed":True,
                "receipt_sha256":expected["receipt_sha256"],
                "local_source_match":True,"independent_attestation":False}
    except (ValueError,TypeError,KeyError,OSError,AttributeError,OverflowError,RecursionError):
        return {**_safety(),"replay_passed":False,
                "reason":"INVALID_OR_CHANGED_INPUT_SOURCE_OR_RECEIPT"}
