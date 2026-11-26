"""Fixed walk-forward team-strength diagnostics; prior-date scores only."""
import json
import math
from collections import defaultdict
from datetime import date
from itertools import groupby
from live_core_multi_source import row, unique
from live_core_multi_league_stress import clip, rates, update, paired_ci
from live_core_low_score_calibration import parse, PINS
from consolidated_historical_replay import fetch
from score_distribution_vnext import score_matrix, one_x_two

CONFIGS=(("league_only",None,None),("team_cumulative",None,8),
         ("decay_90_shrink8",90,8),("decay_180_shrink8",180,8),
         ("decay_90_shrink16",90,16),("decay_180_shrink16",180,16))
OUTCOMES=("HOME","DRAW","AWAY")

def clean(rows):
    return unique([row(d,h,a,[x,y]) for d,h,a,x,y in rows])

def team_rates(h,a,H,A,shrink):
    return (clip(((h[1]+shrink*H)/(h[0]+shrink))*((a[5]+shrink*H)/(a[3]+shrink))/H),
            clip(((a[4]+shrink*A)/(a[3]+shrink))*((h[2]+shrink*A)/(h[0]+shrink))/A))

def forecast(train,test):
    train,test=clean(train),clean(test)
    if len(train)<50 or not test or train[-1][0]>=test[0][0]:
        raise ValueError("INSUFFICIENT_OR_OVERLAPPING_SEASONS")
    boundary=test[0][0]
    histories={name:defaultdict(lambda:[0.]*6) for name,_,s in CONFIGS if s is not None}
    n=gh=ga=0
    previous=None
    observations=[]
    for day,g in groupby(train+test,key=lambda r:r[0]):
        batch=list(g)
        current=date.fromisoformat(day)
        for name,half,shrink in CONFIGS:
            if half is not None and previous is not None:
                factor=2**(-(current-previous).days/half)
                for v in histories[name].values():
                    for i in range(6):v[i]*=factor
        previous=current
        if day>=boundary:
            H,A=clip(gh/n),clip(ga/n)
            for _,home,away,x,y in batch:
                predictions={}
                for name,_,shrink in CONFIGS:
                    if shrink is None: h,a=H,A
                    else: h,a=team_rates(histories[name][home],histories[name][away],H,A,shrink)
                    grid=score_matrix(h,a)
                    p=one_x_two(grid)
                    under=math.fsum(v for i,r in enumerate(grid) for j,v in enumerate(r) if i+j<=2)
                    predictions[name]=(tuple(p[k] for k in OUTCOMES),under,h,a)
                observations.append((day,home,away,x,y,predictions))
        # All results from the same date enter AFTER every forecast that date.
        for _,home,away,x,y in batch:
            for hist in histories.values():update(hist,home,away,x,y)
            n+=1;gh+=x;ga+=y
    return observations

def report(train,test):
    obs=forecast(train,test)
    stats={}
    per_model={}
    for name,_,_ in CONFIGS:
        values=[]
        for day,_,_,x,y,pred in obs:
            p,u,_,_=pred[name];k=0 if x>y else 1 if x==y else 2
            values.append((-math.log(max(p[k],1e-15)),math.fsum((v-(i==k))**2 for i,v in enumerate(p)),(u-(x+y<=2))**2))
        per_model[name]=values
        stats[name]=dict(zip(("log_loss","brier","under25_brier"),(math.fsum(v[i] for v in values)/len(obs) for i in range(3))))
    for name,_,_ in CONFIGS:
        weeks=defaultdict(list)
        for r,b,c in zip(obs,per_model["team_cumulative"],per_model[name]):
            weeks[date.fromisoformat(r[0]).isocalendar()[:2]].append(b[0]-c[0])
        stats[name]["baseline_minus_candidate_log_loss_ci95"]=paired_ci([(math.fsum(v),len(v)) for _,v in sorted(weeks.items())])
    return {"train_n":len(train),"assessment_n":len(obs),"models":stats,
            "baseline":"team_cumulative","fixed_configs":[list(x) for x in CONFIGS],
            "selected_model":None,"same_day_results_excluded":True,
            "historical_only":True,"assessment_previously_inspected":True,
            "independent_prospective_validation":False,"verified_forward_sample_credit":0,
            "model_calibrated":False,"positive_ev_verified":False,
            "production_recommendations":"DISABLED","status":"HOLD"}

if __name__=="__main__":
    rows=[parse(fetch(s),s) for s in ("2020-21","2021-22")]
    print(json.dumps(report(*rows),sort_keys=True,allow_nan=False))
