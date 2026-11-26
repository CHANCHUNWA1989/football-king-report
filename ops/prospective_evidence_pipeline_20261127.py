"""Research-only evidence pipeline: derive paired scores from sealed raw records.

Anchors, provider registry and timestamps are caller assertions, not attestations.
The 1X2 archive cannot support exact-score or goal-tail performance guardrails.
"""
from collections.abc import Mapping
from ops.prospective_archive_audit_20261127 import audit,canonical_manifest,seal,GENESIS
from ops.live_snapshot_market_audit_20261126 import aware
from ops.live_paired_holdout_20261127 import evaluate_holdout
from ops.research_promotion_triage_20261127 import triage

def _settlements(records,aliases,m,manifest_hash,head,evaluated):
    if not isinstance(records,list): raise ValueError("invalid settlement archive")
    previous=GENESIS;out={};last=None
    for record in records:
        if not isinstance(record,Mapping) or set(record)!={"entry","previous","sha256"}:
            raise ValueError("invalid settlement record")
        e=record["entry"]
        if not isinstance(e,Mapping) or set(e)!={"fixture_id","manifest_sha256","settled_at","observed_at","score","status"}:
            raise ValueError("invalid settlement schema")
        if record!=seal(e,previous): raise ValueError("broken settlement chain")
        previous=record["sha256"]
        fid=aliases.get(e["fixture_id"])
        if fid not in m["fixtures"] or fid in out or e["manifest_sha256"]!=manifest_hash:
            raise ValueError("duplicate or unregistered settlement")
        if e["status"]!="FULL_TIME_REGULATION": raise ValueError("unsupported settlement scope")
        f=e["score"]
        if not isinstance(f,list) or len(f)!=2 or any(type(v) is not int or not 0<=v<=30 for v in f):
            raise ValueError("invalid regulation score")
        settled=aware(e["settled_at"]);observed=aware(e["observed_at"])
        if not aware(m["fixtures"][fid])<settled<=observed<=evaluated or (last is not None and observed<last):
            raise ValueError("settlement chronology violation")
        last=observed;out[fid]=e
    if previous!=head: raise ValueError("settlement anchor mismatch")
    if set(out)!=set(m["fixtures"]): raise ValueError("incomplete settlement cohort")
    return out

def review(manifest,forecasts,settlements,aliases,prior,forecast_head,settlement_head,evaluated_at):
    """No caller-supplied performance metrics or verification flags accepted."""
    result={"status":"HOLD","deployment":"HOLD","recommendations":"DISABLED",
            "promotion_authorized":False,"prospective_verified":False,
            "source_attestation_verified":False,"positive_ev_verified":False,
            "metrics":None,"reasons":[]}
    try:
        evaluated=aware(evaluated_at)
        a=audit(manifest,forecasts,aliases,prior,forecast_head)
        result["forecast_audit"]=a
        if a["reasons"]:
            result["reasons"]=a["reasons"];return result
        m=canonical_manifest(manifest,aliases)
        s=_settlements(settlements,aliases,m,a["manifest_sha256"],settlement_head,evaluated)
        fs={(aliases[r["entry"]["fixture_id"]],r["entry"]["model_id"]):r["entry"] for r in forecasts}
        paired=[]
        for fid,decision in sorted(m["fixtures"].items()):
            e=s[fid];h,k=e["score"]
            row={"fixture_id":fid,"decision_at":decision,"settled_at":e["settled_at"],
                 "outcome":0 if h>k else 1 if h==k else 2}
            for side in ("baseline","challenger"):
                model=m[side+"_id"];f=fs[fid,model]
                row[side]=f["probabilities"];row[side+"_id"]=model
                for field in ("issued_at","trained_through","features_through"):
                    row[side+"_"+field]=f[field]
            paired.append(row)
        pm={**m,"fixtures":[{"fixture_id":fid,"decision_at":d} for fid,d in sorted(m["fixtures"].items())]}
        metrics=evaluate_holdout(pm,paired)
        result["metrics"]=metrics
        # The two manifest serializers differ; bind promotion to the archive digest.
        report={"cohort_sha256":a["overlap"]["cohort_sha256"],
                "manifest_sha256":a["manifest_sha256"],"forecast_archive_sha256":forecast_head,
                "settlement_archive_sha256":settlement_head,"frozen_at":m["frozen_at"],
                "first_decision_at":min(m["fixtures"].values()),"last_decision_at":max(m["fixtures"].values()),
                "evaluated_at":evaluated_at,"baseline_id":m["baseline_id"],"challenger_id":m["challenger_id"],
                "n":metrics["n"],"weeks":metrics["utc_weeks"],"complete_paired_cohort":True,
                "deltas":metrics["mean_challenger_minus_baseline"],"intervals":metrics["intervals"],
                "retrospective_only":None,"comparator_role":None,"preregistered_primary":None,
                "multiplicity_controlled":False,"independent_reproduction":False}
        gate=triage(report,[])
        result["triage"]=gate
        result["reasons"]=sorted(set(gate["reasons"])|{"EXTERNAL_ANCHORS_UNAUTHENTICATED",
            "SETTLEMENT_SOURCE_UNAUTHENTICATED","SCORE_DISTRIBUTION_GUARDRAILS_MISSING",
            "FIXTURE_REGISTRY_UNAUTHENTICATED"})
        return result
    except (ValueError,TypeError,KeyError,OverflowError):
        result["reasons"]=["INVALID_EVIDENCE"];return result
