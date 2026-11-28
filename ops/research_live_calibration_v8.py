"""Research calibration on replayable live bundles, never a production model.
All clocks and source claims remain unauthenticated. No fitting on legacy ledger.
"""
from collections import Counter
from .research_live_evidence_v3 import verify_bundle, settle
from .research_unified_live_v2 import utc, digest, text
from .research_multimodel_v1 import multiclass_brier, log_loss

KEYS=("home","draw","away")
WEIGHTS=(0.0,0.1,0.25,0.5,0.75,1.0)
MIN_TRAIN=100
MIN_TEST=100
MIN_DAYS=20

def blend(b,d,w):
    return {k:(1-w)*b[k]+w*d[k] for k in KEYS}

def score(rows,w):
    if not rows:
        return None
    n=len(rows)
    predictions=[(blend(b,d,w),y) for _,b,d,y,_ in rows]
    return {"n":n,"brier":sum(multiclass_brier(p,y) for p,y in predictions)/n,
            "log_loss":sum(log_loss(p,y) for p,y in predictions)/n}

def base_report():
    return {"schema":"live-calibration-v8","status":"HOLD","production_recommendations":"DISABLED",
            "source_authenticity_verified":False,"independent_oos_proven":False,
            "calibrated_for_production":False,"model_promotion_allowed":False,
            "market_comparison_performed":False,"candidate_only":True}

def legacy_readiness(doc):
    """Legacy prematch outcomes cannot substitute for sealed live observations."""
    if not isinstance(doc,dict) or doc.get("schema")!="football-king-forward-research-1" or not isinstance(doc.get("samples"),list) or type(doc.get("n")) is not int or doc["n"]!=len(doc["samples"]):
        raise ValueError("invalid legacy ledger")
    return {**base_report(),"legacy_candidate_count":len(doc["samples"]),
            "live_training_eligible_count":0,"reason":"LEGACY_PREMATCH_NOT_LIVE_REPLAY_EVIDENCE"}

def calibrate(pairs, *, model_release, train_start, train_cutoff, test_end, as_of):
    """Fit one bounded blend weight on earlier results only, freeze for entire test.
    No league-specific fit or true parameter training of the underlying xG engine.
    Cohort limits are design choices; not a statistical-power guarantee.
    """
    start,cut,end,now=map(utc,(train_start,train_cutoff,test_end,as_of))
    if not start<cut<end<=now or not isinstance(pairs,(list,tuple)) or len(pairs)>10000:
        raise ValueError("invalid cohort")
    text(model_release)
    training=[]; testing=[]; seen=set(); skipped=Counter()
    for bundle,result in pairs:
        if not verify_bundle(bundle) or bundle["model_release"]!=model_release:
            raise ValueError("bundle/release mismatch")
        if result!=settle(bundle,result["observations"],as_of=result["observed_at"]):
            raise ValueError("settlement replay failed")
        t=utc(bundle["as_of"]); r=utc(result["observed_at"])
        if r>now or not start<=t<end or not 20<=bundle["report"]["minute"]<30:
            raise ValueError("outside declared cohort")
        event=bundle["event_id"]
        if event in seen:
            raise ValueError("duplicate fixture")
        seen.add(event)
        b={k:bundle["report"]["baseline"][k] for k in KEYS}
        d={k:bundle["report"]["dynamic"][k] for k in KEYS}
        row=(event,b,d,result["outcome"],t.date().isoformat())
        if t<cut:
            if r>=cut:
                skipped["TRAIN_RESULT_NOT_AVAILABLE_BEFORE_CUTOFF"]+=1
            else:
                training.append(row)
        else:
            testing.append(row)
    td=len({x[4] for x in training}); vd=len({x[4] for x in testing})
    output={**base_report(),"train_n":len(training),"test_n":len(testing),
            "train_days":td,"test_days":vd,"excluded":dict(skipped),
            "train_cutoff":cut.isoformat(),"test_end":end.isoformat(),
            "model_release":model_release,"weights_fitted":False,
            "test_used_for_weight_selection":False}
    if len(training)<MIN_TRAIN or len(testing)<MIN_TEST or min(td,vd)<MIN_DAYS:
        return {**output,"reason":"INSUFFICIENT_REPLAYABLE_COHORT"}
    # Tie-break toward the frozen baseline, never inspect test losses for choice.
    scores=[(score(training,w)["log_loss"],w) for w in WEIGHTS]
    chosen=min(scores)[1]
    policy={"schema":"live-blend-policy-v8","model_release":model_release,
            "train_cutoff":cut.isoformat(),"weight":chosen,
            "training_event_ids":sorted(x[0] for x in training)}
    policy["sha256"]=digest(policy)
    baseline=score(testing,0.0); challenger=score(testing,chosen); dynamic=score(testing,1.0)
    return {**output,"weights_fitted":True,"frozen_policy":policy,
            "test_metrics":{"baseline":baseline,"dynamic":dynamic,"blend":challenger},
            "delta_vs_baseline":{"brier":challenger["brier"]-baseline["brier"],
                                 "log_loss":challenger["log_loss"]-baseline["log_loss"]},
            "reason":"DESCRIPTIVE_REPLAY_ONLY_NOT_INDEPENDENT_VALIDATION"}
