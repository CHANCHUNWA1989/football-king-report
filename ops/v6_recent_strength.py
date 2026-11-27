"""Fixed recent-strength challenger on a separate 2026/27 native retrospective cohort."""
import argparse
from collections import defaultdict
from datetime import datetime,timezone,date
import json
import math
from pathlib import Path
from ops import v5_joint_poisson as joint,v5_dynamic_elo as elo,v5_ml_benchmark as ml,v5_ensemble_competition as e
from ops.v5_native_bundesliga_forward import normalize,fetch,state,feature,WEIGHTS,BERLIN
from ops.v6_accuracy_target import summary,week_ci

THRESHOLD=.50
TARGET=.60
def prior_rows(rows,day):
    return [r for r in rows if r[0]<day]
def updated_rates(old,recent):
    if recent is None:return old
    if any(not .05<=v<=8 for v in (*old,*recent)):raise ValueError("INVALID_RATES")
    return tuple(math.sqrt(x*y) for x,y in zip(old,recent))

def replay(old,new,now):
    local=now.astimezone(BERLIN);season=local.year-int(local.month<7)
    if season!=2026:raise ValueError("FIXED_COHORT_ONLY")
    a=normalize(old,season-1,now,previous=True);b=normalize(new,season,now)
    if a["ids"]&b["ids"]:raise ValueError("CROSS_SEASON_DUPLICATE")
    tr=joint.parse(a["history"]);te=joint.parse(b["history"])
    if not te or max(r[0] for r in tr)>=min(r[0] for r in te):raise ValueError("OVERLAPPING_OR_EMPTY")
    base_model=joint.fit(tr,min(r[0] for r in te))
    train=ml.features(a["history"]);y=[r["y"] for r in train]
    if len(train)<100 or set(y)!={0,1,2}:raise ValueError("INSUFFICIENT_TRAIN")
    models={}
    for k in ml.BACKENDS:
        m=ml.classifier(k);m.fit([r["x"] for r in train],y)
        if list(m.classes_)!=[0,1,2]:raise ValueError("CLASS_ORDER")
        models[k]=m
    groups=defaultdict(list)
    for r in te:groups[r[0]].append(r)
    out=[];excluded=0
    for day in sorted(groups):
        prior=prior_rows(te,day)
        ratings,teams,goals=state(prior,elo)
        # Fixed last 150 prior-season fixtures plus current-season prior days.
        # Same-day fixtures never enter fitting or features.
        refit=joint.fit(tr[-150:]+prior,day)
        for _,h,a,x,y in groups[day]:
            old_rates=joint.rates(base_model,h,a)
            er=elo.rates(prior,day,h,a,ratings,True)
            f=feature(teams,goals,h,a,ml)
            if old_rates is None or er is None or f is None or any(not .05<=v<=8 for v in old_rates):
                excluded+=1;continue
            v={"joint_poisson":e.vec(joint.probability(old_rates)),"dixon_coles":e.dc(*old_rates),
                "dynamic_elo":e.vec(elo.probabilities(*er))}
            for k,m in models.items():v[k]=e.vec([float(z) for z in m.predict_proba([f])[0]])
            r=joint.rates(refit,h,a)
            if r is not None and any(not .05<=z<=8 for z in r):r=None
            updated=updated_rates(old_rates,r)
            cand={**v,"joint_poisson":e.vec(joint.probability(updated)),"dixon_coles":e.dc(*updated)}
            out.append({"date":day.isoformat(),"home":h,"away":a,"y":0 if x>y else 1 if x==y else 2,
                "baseline":e.blend(v,WEIGHTS),"candidate":e.blend(cand,WEIGHTS)})
    return out,len(te),excluded

def report(rows,total,excluded):
    b=[{**r,"base":r["baseline"]} for r in rows];c=[{**r,"base":r["candidate"]} for r in rows]
    s=summary(c,THRESHOLD)
    return {"schema":"v6-4-recent-strength-research-v1","season":2026,"league":"bundesliga",
        "all_finished":total,"eligible":len(rows),"excluded":excluded,"fixed_threshold":THRESHOLD,
        "baseline":summary(b),"candidate":summary(c),"baseline_selected":summary(b,THRESHOLD),
        "candidate_selected":s,"candidate_selected_week_ci":week_ci(c,THRESHOLD),
        "candidate_selected_total_fixture_coverage":s["n"]/total if total else None,
        "target60_point_with_min100":bool(s["n"]>=100 and s["n"]/total>=.20 and s["accuracy"]>=TARGET),
        "historical_reconstructed_not_prospective":True,"source_results_independently_verified":False,
        "market_comparison_available":False,"automatic_promotion":False,"production_recommendations":"DISABLED","status":"HOLD"}

def main():
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);a=p.parse_args()
    old,r1=fetch(2025);new,r2=fetch(2026);now=datetime.now(timezone.utc)
    out=report(*replay(old,new,now));out["source_receipts"]=[r1,r2]
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
