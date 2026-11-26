"""Pinned historical halftime deep-margin sensitivity, not actual odds backtest."""
import json
import math
from datetime import date
from collections import Counter
from asian_handicap_research import TYPES,grade
from deep_handicap_joint_score import _half
from live_core_halftime_dynamics import fetch

LINES=(-1.5,-2.0,-2.25,-2.5,-3.0)
PACE=.85
MODELS=("baseline","pace085")

def validate(rows):
    if not isinstance(rows,list) or not 1<=len(rows)<=380:raise ValueError("ROW_SCOPE")
    seen=set()
    for r in rows:
        if not isinstance(r,(list,tuple)) or len(r)!=7:raise ValueError("ROW_SHAPE")
        day,h,a,i,j,x,y=r
        if not isinstance(day,str) or date.fromisoformat(day).isoformat()!=day:raise ValueError("DATE")
        if any(not isinstance(v,str) or not v.strip() for v in (h,a)) or h==a:raise ValueError("TEAM")
        if any(type(v) is not int or not 0<=v<=25 for v in (i,j,x,y)) or i>x or j>y:raise ValueError("SCORE")
        key=(day,h,a)
        if key in seen:raise ValueError("DUPLICATE")
        seen.add(key)
    return sorted(rows)

def grades(i,j,home_rate,away_rate,side,line,pace):
    if side=="HOME":home_rate*=pace
    else:away_rate*=pace
    out=dict.fromkeys(TYPES,0.0)
    for h,p in enumerate(_half(home_rate)):
        for a,q in enumerate(_half(away_rate)):
            m=max(-25,min(25,i+h-j-a))
            out[grade(max(0,m),max(0,-m),side,line)]+=p*q
    if abs(math.fsum(out.values())-1)>1e-9:raise ValueError("MASS")
    return out

def report(train,test):
    train,test=validate(train),validate(test)
    if max(r[0] for r in train)>=min(r[0] for r in test):raise ValueError("TEMPORAL_OVERLAP")
    rh=math.fsum(r[5]-r[3] for r in train)/len(train)
    ra=math.fsum(r[6]-r[4] for r in train)/len(train)
    # Fixed half-time selection, not inferred bookmaker favourite. Never use
    # final score to select rows or decide the handicap side.
    eligible=[r for r in test if abs(r[3]-r[4])>=2]
    n=len(eligible)
    results={}
    for line in LINES:
        losses={m:[] for m in MODELS}
        actual_counts=Counter()
        for _,_,_,i,j,x,y in eligible:
            side="HOME" if i>j else "AWAY"
            actual=grade(x,y,side,line)
            actual_counts[actual]+=1
            for model,pace in zip(MODELS,(1.,PACE)):
                p=grades(i,j,rh,ra,side,line,pace)
                losses[model].append((math.fsum((p[k]-(k==actual))**2 for k in TYPES),
                                      -math.log(max(1e-15,p[actual]))))
        metrics={m:{k:math.fsum(v[idx] for v in losses[m])/n if n else None
                    for idx,k in enumerate(("brier","log_loss"))} for m in MODELS}
        results[str(line)]={"n":n,"observed_grade_counts":{k:actual_counts[k] for k in TYPES},
                            "metrics":metrics,
                            "candidate_minus_baseline":{k:metrics["pace085"][k]-metrics["baseline"][k] if n else None
                                                        for k in ("brier","log_loss")}}
    return {"schema":"football-king-deep-halftime-historical-v1","train_n":len(train),
            "assessment_n":len(test),"eligible_halftime_leader_n":n,
            "ineligible_halftime_state_n":len(test)-n,
            "train_only_remaining_rates":{"home":rh,"away":ra},"fixed_pace":PACE,
            "by_hypothetical_line":results,"same_fixture_repeated_across_lines":True,
            "selection":"HALFTIME_MARGIN_AT_LEAST_TWO",
            "historical_only":True,"actual_market_lines_verified":False,
            "actual_quotes_verified":False,"missingness_bias_ruled_out":False,
            "model_calibrated":False,"confidence_intervals_available":False,
            "independent_prospective_validation":False,"verified_forward_sample_credit":0,
            "positive_ev_verified":False,"production_recommendations":"DISABLED","status":"HOLD"}

def run():
    return report(fetch("2020-21"),fetch("2021-22"))

if __name__=="__main__":
    print(json.dumps(run(),sort_keys=True,allow_nan=False))
