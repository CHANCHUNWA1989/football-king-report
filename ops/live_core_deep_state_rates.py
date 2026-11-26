"""Train-only state-conditioned goal rates; retrospective exploratory research."""
import json
import math
from collections import Counter
from asian_handicap_research import TYPES,grade
from live_core_deep_halftime_replay import validate,grades,LINES,PACE
from live_core_halftime_dynamics import fetch

SHRINK=50
MODELS=("baseline","pace085","state_shrink50")
SIDES=("HOME","AWAY")

def side(r):
    return "HOME" if r[3]-r[4]>=2 else "AWAY" if r[4]-r[3]>=2 else None

def fit(train):
    train=validate(train)
    pooled=tuple(math.fsum(r[k+2]-r[k] for r in train)/len(train) for k in (3,4))
    groups={}
    for s in SIDES:
        rows=[r for r in train if side(r)==s]
        n=len(rows)
        rates=tuple((math.fsum(r[k+2]-r[k] for r in rows)+SHRINK*p)/(n+SHRINK)
                    for k,p in zip((3,4),pooled))
        groups[s]={"n":n,"rates":rates}
    return pooled,groups

def report(train,test):
    train,test=validate(train),validate(test)
    if max(r[0] for r in train)>=min(r[0] for r in test):raise ValueError("TEMPORAL_OVERLAP")
    pooled,groups=fit(train)
    eligible=[r for r in test if side(r)]
    n=len(eligible)
    results={}
    for line in LINES:
        values={m:[] for m in MODELS};counts=Counter()
        for r in eligible:
            _,_,_,i,j,x,y=r;s=side(r)
            ygrade=grade(x,y,s,line);counts[ygrade]+=1
            for m,rates,pace in (("baseline",pooled,1.),("pace085",pooled,PACE),
                                 ("state_shrink50",groups[s]["rates"],1.)):
                p=grades(i,j,*rates,s,line,pace)
                values[m].append((math.fsum((p[k]-(k==ygrade))**2 for k in TYPES),
                                  -math.log(max(1e-15,p[ygrade]))))
        metrics={m:{k:math.fsum(v[i] for v in values[m])/n if n else None
                    for i,k in enumerate(("brier","log_loss"))} for m in MODELS}
        results[str(line)]={"n":n,"grades":{k:counts[k] for k in TYPES},"metrics":metrics,
            "state_minus_baseline":{k:metrics["state_shrink50"][k]-metrics["baseline"][k] if n else None for k in ("brier","log_loss")}}
    for m in MODELS:
        for k in ("brier","log_loss"):
            a=results["-2.0"]["metrics"][m][k];b=results["-2.25"]["metrics"][m][k]
            if (a is None)!=(b is None) or (a is not None and abs(a-b)>1e-12):raise ValueError("EQUIVALENT_GRADE_CONFLICT")
    return {"schema":"football-king-deep-state-rates-v1","train_n":len(train),"assessment_n":len(test),
            "eligible_n":n,"excluded_n":len(test)-n,"shrink_pseudo_matches":SHRINK,
            "pooled_train_rates":list(pooled),"train_groups":groups,
            "assessment_group_counts":{s:sum(side(r)==s for r in eligible) for s in SIDES},
            "by_hypothetical_line":results,"distinct_grade_partitions":4,
            "previously_examined_assessment_season":True,"exploratory_only":True,
            "actual_market_lines_verified":False,"confidence_intervals_available":False,
            "causal_tactical_effect_identified":False,"verified_forward_sample_credit":0,
            "model_calibrated":False,"positive_ev_verified":False,
            "production_recommendations":"DISABLED","status":"HOLD"}

def run():return report(fetch("2020-21"),fetch("2021-22"))
if __name__=="__main__":print(json.dumps(run(),sort_keys=True,allow_nan=False))
