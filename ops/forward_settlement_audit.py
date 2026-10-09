"""Point-in-time forward prediction and independently settled result audit.

Read-only JSON input. Never treats historical backfills as live forward evidence.
No model promotion, betting execution, or implied EV.
"""
import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

SCHEMA="football-king-forward-settlement-v1"
MIN_FORWARD=300

def timestamp(value):
    if not isinstance(value,str):
        raise ValueError("MISSING_UTC_TIMESTAMP")
    dt=datetime.fromisoformat(value.replace("Z","+00:00"))
    if dt.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return dt.astimezone(timezone.utc)

def audit(records, *, now=None):
    if not isinstance(records,list) or len(records)>100000:
        raise ValueError("INVALID_RECORDS")
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    reasons={}
    def reject(reason):
        reasons[reason]=reasons.get(reason,0)+1
    seen=set()
    accepted=[]
    for row in records:
        if not isinstance(row,dict):
            reject("INVALID_RECORD")
            continue
        event=row.get("event_id")
        model=row.get("model_version")
        market=row.get("market")
        if not all(isinstance(x,str) and x.strip() for x in (event,model,market)):
            reject("MISSING_IDENTITY")
            continue
        identity=(event,model,market)
        if identity in seen:
            reject("DUPLICATE_EVENT_MODEL_MARKET")
            continue
        try:
            predicted=timestamp(row.get("prediction_created_at_utc"))
            kickoff=timestamp(row.get("kickoff_utc"))
            settled=timestamp(row.get("settled_at_utc"))
            source_time=timestamp(row.get("source_snapshot_at_utc"))
        except (ValueError,TypeError,OverflowError):
            reject("INVALID_TIMESTAMP")
            continue
        if not (source_time<=predicted<kickoff<settled<=now):
            reject("LOOKAHEAD_OR_INVALID_CHRONOLOGY")
            continue
        if row.get("immutable_prediction_record") is not True:
            reject("NO_IMMUTABLE_FORWARD_PROOF")
            continue
        if row.get("independent_settlement_verified") is not True:
            reject("UNVERIFIED_SETTLEMENT")
            continue
        if row.get("historical_backfill") is not False:
            reject("BACKFILL_NOT_FORWARD")
            continue
        p=row.get("predicted_probability")
        outcome=row.get("settled_binary_outcome")
        if type(p) not in (float,int) or not math.isfinite(p) or not 0<=p<=1:
            reject("INVALID_PROBABILITY")
            continue
        if type(outcome) is not int or outcome not in (0,1):
            reject("INVALID_BINARY_SETTLEMENT")
            continue
        baseline=row.get("market_baseline_probability")
        if type(baseline) not in (float,int) or not math.isfinite(baseline) or not 0<=baseline<=1:
            reject("INVALID_MARKET_BASELINE")
            continue
        seen.add(identity)
        accepted.append((float(p),outcome,float(baseline)))
    n=len(accepted)
    brier=sum((p-y)**2 for p,y,_ in accepted)/n if n else None
    market_brier=sum((m-y)**2 for _,y,m in accepted)/n if n else None
    improvement=market_brier-brier if n else None
    # Even a positive average improvement is insufficient for promotion.
    return {"schema":SCHEMA,"status":"RESEARCH_ONLY" if n else "HOLD",
            "submitted_records":len(records),"independent_forward_samples":0,
            "candidate_forward_samples":n,"authenticated_forward_samples":0,
            "independent_forward_samples_are_self_attested":True,
            "candidate_metrics_only":True,
            "rejected_records":len(records)-n,"reject_reasons":reasons,
            "brier_score":round(brier,8) if n else None,
            "market_baseline_brier_score":round(market_brier,8) if n else None,
            "brier_improvement_vs_market":round(improvement,8) if n else None,
            "minimum_forward_samples_required":MIN_FORWARD,
            "sample_count_threshold_met":False,
            "candidate_sample_count_threshold_met":n>=MIN_FORWARD,
            "statistical_significance_verified":False,
            "calibration_verified":False,
            "leakage_free_independent_audit_verified":False,
            "positive_ev_proven":False,
            "model_promotion_allowed":False,
            "production_recommendations":"DISABLED",
            "recommendation":None}

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",default="forward-settlement-audit.json")
    a=p.parse_args(argv)
    records=json.loads(Path(a.input).read_text(encoding="utf-8"))
    result=audit(records)
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"independent_forward_samples":result["independent_forward_samples"],
                      "rejected_records":result["rejected_records"],
                      "model_promotion_allowed":False},ensure_ascii=False))

if __name__=="__main__":
    main()
