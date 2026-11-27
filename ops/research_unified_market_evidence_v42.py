"""V42: exact declared Asian quote evidence binding across V3 and V35.
Strict subset policy: exactly two complete publisher snapshots of four rows.
1X2 has no counterpart in V35 and is never claimed independently cross-checked.
No external authentication, executable value, or production permission.
"""
from .research_unified_execution_v41 import run as run_v41
from .research_snapshot_replay_v3 import _decode
from .research_unified_cutoff_v39 import utc
from .research_unified_prematch_replay_v35 import digest
from math import isfinite

def label(v):
    if type(v) is not str or not v.strip() or len(v)>200:
        raise ValueError("invalid declared label")
    return v.strip().casefold()

def number(v):
    if type(v) not in (int,float) or not isfinite(v):
        raise ValueError("invalid number")
    return float(v)

def key(m,s,line):
    return (m,s,number(line))

def evidence(record, raw):
    p=_decode(raw)
    if p["fixture_id"]!=record["event_id"] or utc(p["kickoff"])!=utc(record["kickoff"]):
        raise ValueError("fixture mismatch")
    h,t=number(record["handicap_line"]),number(record["totals_line"])
    expected={("handicap","home",h),("handicap","away",h),
              ("totals","over",t),("totals","under",t)}
    if len(p["snapshots"])!=2 or len(record["quotes"])!=8:
        raise ValueError("strict two-publisher coverage required")
    a={}
    for snap in p["snapshots"]:
        pub,up,book=map(label,(snap["publisher"],snap["upstream"],snap["bookmaker"]))
        clock=utc(snap["observed_at"]).isoformat()
        keys=set()
        for q in snap["asian"]:
            k=key(q["market"],q["selection"],q["line"])
            full=(pub,up,book,clock,*k)
            if k in keys or full in a:
                raise ValueError("duplicate snapshot row")
            keys.add(k);a[full]=number(q["decimal_odds"])
        if keys!=expected:
            raise ValueError("missing or extra Asian lines")
    b={}
    for q in record["quotes"]:
        if q["event_id"]!=record["event_id"] or utc(q["kickoff_at"])!=utc(record["kickoff"]):
            raise ValueError("quote fixture mismatch")
        k=key(q["market"],q["selection"],q["line"])
        full=(*map(label,(q["source"],q["upstream_provider"],q["bookmaker"])),
              utc(q["observed_at"]).isoformat(),*k)
        if k not in expected or full in b:
            raise ValueError("extra or duplicate quote row")
        b[full]=number(q["decimal_odds"])
    if a!=b:
        raise ValueError("cross-path quote mismatch")
    return digest([[*k,v] for k,v in sorted(a.items())])

def run(**kwargs):
    out={"schema":"unified-market-evidence-v42","status":"HOLD",
         "production_recommendations":"DISABLED","execution_passed":False,
         "source_identity_authenticated":False,"external_timestamp_verified":False,
         "training_admission":False,"qualified_for_production":False,
         "verified_executable_ev":False,"independent_oos_proven":False,
         "cross_path_market_equality_verified":False,
         "cross_path_asian_equality_verified":False,
         "cross_path_1x2_equality_verified":False}
    try:
        base=run_v41(**kwargs)
        if base.get("execution_passed") is not True or any(base.get(k)!=v for k,v in out.items()
            if k not in ("schema","execution_passed","cross_path_asian_equality_verified","cross_path_1x2_equality_verified")):
            raise ValueError("V41 execution rejected")
        records={r["event_id"]:r for r in kwargs["records"]}
        cases=kwargs.get("live_cases") or {}
        proofs={}
        for event,case in sorted(cases.items()):
            proofs[event]=evidence(records[event],case["inputs"]["prematch_raw"])
        if len(proofs)!=base["live_fixture_count"]:
            raise ValueError("coverage mismatch")
        result={**out,"execution_passed":True,
                "cross_path_asian_equality_verified":bool(proofs),
                "matched_live_fixture_count":len(proofs),
                "uncompared_prematch_fixture_count":len(records)-len(proofs),
                "asian_evidence_sha256":proofs,"v41_execution":base}
        result["local_execution_sha256"]=digest(result)
        return result
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError,RecursionError):
        return {**out,"reason":"INVALID_OR_UNMATCHED_MARKET_EVIDENCE"}
