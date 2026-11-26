"""Score-distribution archive v2 and paired research evaluation.

Finite regulation score support 0..30 per side; missing cells are zero.
No source or external anchor authentication; no production authorization.
"""
from collections import defaultdict
from collections.abc import Mapping
from math import fsum,isfinite,log
from random import Random
from ops.prospective_archive_audit_20261127 import canonical_manifest,digest,seal,GENESIS,overlap,identifier
from ops.prospective_evidence_pipeline_20261127 import _settlements
from ops.live_snapshot_market_audit_20261126 import aware
from ops.live_unified_market_probabilities_20261127 import unified_markets
from ops.research_promotion_triage_20261127 import triage,METRICS
from ops.live_paired_holdout_20261127 import _quantile

SCHEMA="REGULATION_SCORE_GRID_V2"
AH=(-1.75,-.75,.25)
OU=(1.75,2.75,3.75)
DRAWS=2000

def grid_from_cells(cells):
    if not isinstance(cells,list) or not 1<=len(cells)<=961:
        raise ValueError("invalid score cells")
    g={}
    for row in cells:
        if not isinstance(row,list) or len(row)!=3: raise ValueError("invalid cell")
        h,a,p=row
        if any(type(v) is not int or not 0<=v<=30 for v in (h,a)) or (h,a) in g:
            raise ValueError("invalid or duplicate score")
        if type(p) not in (int,float) or not isfinite(p) or not 0<=p<=1:
            raise ValueError("invalid probability")
        g[h,a]=p
    mass=fsum(g.values())
    if abs(mass-1)>1e-10: raise ValueError("invalid mass")
    return {k:v/mass for k,v in g.items()}

def manifest_hash(m):
    return digest({"schema":SCHEMA,"manifest":m})

def derive(cells):
    g=grid_from_cells(cells)
    markets=unified_markets(g,AH,OU,scope="FULL_MATCH")
    markets["five_plus"]=fsum(v for (h,a),v in g.items() if h+a>=5)
    return g,markets

def losses(g,m,f):
    h,a=f;y=0 if h>a else 1 if h==a else 2
    p=m["one_x_two"]
    return (-log(max(p[y],1e-15)),fsum((v-(i==y))**2 for i,v in enumerate(p)),
            ((p[0]-(y==0))**2+(p[0]+p[1]-(y<=1))**2)/2,
            -log(max(g.get((h,a),0),1e-15)),(m["five_plus"]-(h+a>=5))**2)

def uncertainty(pairs):
    groups=defaultdict(list)
    for day,delta in pairs: groups[day].append(delta)
    blocks=[(len(groups[k]),[fsum(v[i] for v in groups[k]) for i in range(5)]) for k in sorted(groups)]
    n=len(pairs)
    means={m:fsum(b[1][i] for b in blocks)/n for i,m in enumerate(METRICS)}
    if n<100 or len(blocks)<20: return means,None,len(blocks)
    rng=Random(20261127);samples=[[] for _ in METRICS]
    for _ in range(DRAWS):
        s=[blocks[rng.randrange(len(blocks))] for _ in blocks]
        size=sum(b[0] for b in s)
        for i in range(5): samples[i].append(fsum(b[1][i] for b in s)/size)
    return means,{m:[_quantile(samples[i],.025),_quantile(samples[i],.975)] for i,m in enumerate(METRICS)},len(blocks)

def review(manifest,forecasts,settlements,aliases,prior,forecast_head,settlement_head,evaluated_at):
    result={"status":"HOLD","deployment":"HOLD","recommendations":"DISABLED",
            "promotion_authorized":False,"prospective_verified":False,"positive_ev_verified":False,
            "source_attestation_verified":False,"metrics":None,"reasons":[]}
    try:
        m=canonical_manifest(manifest,aliases);md=manifest_hash(m)
        o=overlap([r["fixture_id"] for r in manifest["fixtures"]],prior,aliases)
        if o["overlap_count"]:
            result["reasons"]=["KNOWN_COHORT_OVERLAP"];return result
        evaluated=aware(evaluated_at)
        if not isinstance(forecasts,list): raise ValueError("invalid archive")
        previous=GENESIS;last=None;fs={}
        for r in forecasts:
            if not isinstance(r,Mapping) or set(r)!={"entry","previous","sha256"}: raise ValueError("invalid record")
            e=r["entry"]
            if not isinstance(e,Mapping) or set(e)!={"schema","fixture_id","model_id","manifest_sha256","issued_at","features_through","trained_through","score_cells"}:
                raise ValueError("invalid forecast schema")
            if r!=seal(e,previous): raise ValueError("broken forecast chain")
            previous=r["sha256"]
            fid=aliases.get(identifier(e["fixture_id"]));model=identifier(e["model_id"])
            if e["schema"]!=SCHEMA or e["manifest_sha256"]!=md or fid not in m["fixtures"] or model not in (m["baseline_id"],m["challenger_id"]) or (fid,model) in fs:
                raise ValueError("unregistered or duplicate forecast")
            issue=aware(e["issued_at"])
            if not aware(e["trained_through"])<=aware(m["frozen_at"])<=issue<=aware(m["fixtures"][fid]) or not aware(e["features_through"])<=issue or (last is not None and issue<last):
                raise ValueError("forecast chronology")
            last=issue;fs[fid,model]=derive(e["score_cells"])
        if previous!=forecast_head: raise ValueError("forecast anchor mismatch")
        if set(fs)!={(f,k) for f in m["fixtures"] for k in (m["baseline_id"],m["challenger_id"])}:
            raise ValueError("incomplete forecasts")
        s=_settlements(settlements,aliases,m,md,settlement_head,evaluated)
        pairs=[]
        for fid,day in sorted(m["fixtures"].items()):
            f=s[fid]["score"]
            b,c=(losses(*fs[fid,m[side+"_id"]],f) for side in ("baseline","challenger"))
            pairs.append((aware(day).isocalendar()[:2],tuple(y-x for x,y in zip(b,c))))
        means,ci,weeks=uncertainty(pairs)
        report={"cohort_sha256":o["cohort_sha256"],"manifest_sha256":md,
                "forecast_archive_sha256":forecast_head,"settlement_archive_sha256":settlement_head,
                "frozen_at":m["frozen_at"],"first_decision_at":min(m["fixtures"].values()),
                "last_decision_at":max(m["fixtures"].values()),"evaluated_at":evaluated_at,
                "baseline_id":m["baseline_id"],"challenger_id":m["challenger_id"],
                "n":len(pairs),"weeks":weeks,"complete_paired_cohort":True,
                "deltas":means,"intervals":ci,"retrospective_only":None,"comparator_role":None,
                "preregistered_primary":None,"multiplicity_controlled":False,"independent_reproduction":False}
        gate=triage(report,[])
        result.update(metrics={"n":len(pairs),"weeks":weeks,"deltas":means,"intervals":ci,
                               "intervals_exploratory":True,"score_support_max":30},
                      triage=gate,reasons=sorted(set(gate["reasons"])|{"EXTERNAL_ANCHORS_UNAUTHENTICATED",
                        "SETTLEMENT_SOURCE_UNAUTHENTICATED","FIXTURE_REGISTRY_UNAUTHENTICATED"}))
        return result
    except (ValueError,TypeError,KeyError,OverflowError):
        result["reasons"]=["INVALID_EVIDENCE"];return result
