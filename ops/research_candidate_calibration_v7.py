"""Read-only comparison of existing sealed A/B/C and market candidate vectors.
No weight fitting, backfilling, authentication or model promotion.
"""
import argparse
import json
import math
from pathlib import Path
from .research_candidate_gap_v6 import audit, stamp, vector
from .research_live_intake_v4 import decode, MAX_BYTES
from .model_ab import matches_sealed as valid_b
from .model_market_challenger import matches_sealed as valid_c

LABELS={"A":"p","B":"ab","C":"c","market":"m"}

def metrics(rows):
    n=len(rows)
    if not n:
        return {"n":0,"models":{}}
    models={}
    for name,field in LABELS.items():
        brier=logloss=rps=0.0
        correct=0
        calibration=[]
        for row in rows:
            p=vector(row[field]); y=row["y"]
            brier+=sum((v-(i==y))**2 for i,v in enumerate(p))
            logloss-=math.log(max(p[y],1e-15))
            rps+=((p[0]-(y==0))**2+(p[0]+p[1]-(y<=1))**2)/2
            choice=max(range(3),key=lambda i:p[i])
            correct+=int(choice==y)
        for j in range(3):
            bins=[]
            for k in range(10):
                group=[(r[field][j],int(r["y"]==j)) for r in rows
                       if min(9,int(10*r[field][j]))==k]
                if group:
                    bins.append({"bin":k,"n":len(group),
                                 "mean_probability":sum(x for x,_ in group)/len(group),
                                 "observed_frequency":sum(y for _,y in group)/len(group)})
            calibration.append(bins)
        models[name]={"brier":brier/n,"log_loss":logloss/n,"rps":rps/n,
                      "accuracy":correct/n,"class_reliability":calibration}
    for name in ("A","B","C"):
        models[name]["delta_brier_vs_market"]=models[name]["brier"]-models["market"]["brier"]
        models[name]["delta_log_loss_vs_market"]=models[name]["log_loss"]-models["market"]["log_loss"]
    return {"n":n,"models":models}

def compare(raw):
    base={"schema":"candidate-calibration-audit-v7","status":"HOLD",
          "production_recommendations":"DISABLED","authenticated_samples":0,
          "independent_oos_proven":False,"calibration_verified":False,
          "weights_fitted":False,"model_promotion_allowed":False,
          "market_same_cutoff_proven":False,"metrics_descriptive_only":True}
    report=audit(raw)
    if not report.get("structural_audit_passed"):
        return {**base,"structural_audit_passed":False,"reason":"INVALID_LEDGER"}
    rows=decode(raw)["samples"]
    paired=[]; missing=invalid=0
    for r in rows:
        if not all(k in r for k in ("ab","ab_model","c","c_model")):
            missing+=1
            continue
        if not valid_b(r["p"],r["ab"],r["ab_model"]) or not valid_c(r["p"],r["m"],r["c"],r["c_model"]):
            invalid+=1
            continue
        paired.append(r)
    def age(r):
        return (stamp(r["forecast_utc"])-stamp(r["market_utc"])).total_seconds()/3600
    def by_age(limit):
        return metrics([r for r in paired if age(r)<=limit])
    return {**base,"structural_audit_passed":True,"ledger_sha256":report["ledger_sha256"],
            "ledger_checked_utc":report["ledger_checked_utc"],
            "candidate_count":len(rows),"missing_challenger_count":missing,
            "invalid_challenger_count":invalid,
            "paired":metrics(paired),"market_age_le_1h":by_age(1),"market_age_le_6h":by_age(6),
            "by_league":{l:metrics([r for r in paired if r["league"]==l]) for l in sorted({r["league"] for r in paired})},
            "selection_bias_possible":True,
            "notice":"Recorded outcomes unverified; age filters are diagnostics, not matched information cutoffs. No new or optimized forecast."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--ledger",type=Path,default=Path("evidence/settled.json"))
    a=p.parse_args()
    with a.ledger.open("rb") as stream:
        report=compare(stream.read(MAX_BYTES+1))
    print(json.dumps(report,sort_keys=True,allow_nan=False))
    return 0 if report["structural_audit_passed"] else 2

if __name__=="__main__":
    raise SystemExit(main())
