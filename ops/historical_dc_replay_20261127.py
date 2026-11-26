"""Offline three-season Dixon-Coles correction of dynamic Poisson rates."""
from itertools import groupby
from math import fsum,log
from pathlib import Path
from ops.historical_season_replay_20261127 import load_season,_score,METRICS
from ops.historical_fair_model_replay_20261127 import TeamCounts
from ops.historical_elo_replay_20261127 import EARLIER
from ops.historical_multileague_replay_20261127 import MANIFEST
from ops.live_score_challenger_20261127 import score_grid

EXTRA={
    "NL":("nl.1.json",306,"abec80d7d0be7e5d9c76c3ab58854b149c5a1a5f","120f472510c3565f08affc248694d1953b542b08","668124659dac4fe9ab3a956a7b72b8b91b7c7bbb"),
    "PT":("pt.1.json",306,"8efa7fb527a5e4121708e6249133b978161d09b4","ba1b9a9427cc003d747895ff8385f51d588939f2","1d210317fba610536c4fad676cbb1a46b36413e3"),
}
def tau(mu,rho):
    h,a=mu
    return (1-h*a*rho,1+h*rho,1+a*rho,1-rho)

def factor(f,t):
    return t[2*f[0]+f[1]] if max(f)<=1 else 1

def fit(rows):
    if not rows: raise ValueError("empty calibration")
    best=(0.0,0.0)
    for k in range(-15,16):
        r=k/100
        ts=[tau(mu,r) for mu,_ in rows]
        if any(min(t)<=0 for t in ts): continue
        loss=-fsum(log(factor(f,t)) for (_,f),t in zip(rows,ts))
        if loss<best[1]-1e-12: best=(r,loss)
    return best[0],best[1]/len(rows)

def dated_rates(rows,counts):
    result=[]
    for _,batch in groupby(sorted(rows,key=lambda r:r[0]),key=lambda r:r[0]):
        batch=list(batch)
        for _,h,a,f in batch:
            mu=(counts.pool[0]*counts.strength(h,0,1)*counts.strength(a,1,2),
                counts.pool[1]*counts.strength(a,1,1)*counts.strength(h,0,2))
            result.append((mu,f))
        counts.update(batch)
    return result

def evaluate(train,cal,test):
    if not train or not cal or not test or max(r[0] for r in train)>=min(r[0] for r in cal) or max(r[0] for r in cal)>=min(r[0] for r in test):
        raise ValueError("strict three-season separation required")
    pool=[fsum(r[3][i] for r in train)/len(train) for i in (0,1)]
    if min(pool)<=0: raise ValueError("invalid pool")
    counts=TeamCounts(pool);counts.update(train)
    rho,cal_delta=fit(dated_rates(cal,counts))
    rows=dated_rates(test,counts)
    losses=[[],[]];correct=[0,0];draw=[[],[]];actual=0;fallback=0
    for mu,f in rows:
        r=rho
        if min(tau(mu,r))<=0: r=0;fallback+=1
        y=0 if f[0]>f[1] else 1 if f[0]==f[1] else 2
        actual+=int(y==1)
        for k,rr in enumerate((0,r)):
            g=score_grid((0,0),*mu,rr)
            p=[fsum(v for (h,a),v in g.items() if (0 if h>a else 1 if h==a else 2)==j) for j in range(3)]
            losses[k].append((*_score(p,y),-log(max(g.get(f,0),1e-15))))
            correct[k]+=int(max(range(3),key=p.__getitem__)==y);draw[k].append(p[1])
    metrics=(*METRICS,"exact_score_log_loss")
    return {"train":len(train),"cal":len(cal),"test":len(test),"rho":rho,"cal_delta":cal_delta,
            "metrics":[{m:fsum(v[j] for v in rs)/len(test) for j,m in enumerate(metrics)} for rs in losses],
            "correct":correct,"draw_pred":[fsum(x)/len(test) for x in draw],"draw_actual":actual/len(test),
            "fallback":fallback,"retrospective_only":True,"positive_ev_verified":False,
            "deployment":"HOLD","recommendations":"DISABLED"}

def run(root):
    specs={k:(name,(EARLIER[k][0],n,n),(EARLIER[k][1],s1,s2)) for k,(name,n,s1,s2) in MANIFEST.items()}
    specs.update({k:(name,(n,n,n),(s0,s1,s2)) for k,(name,n,s0,s1,s2) in EXTRA.items()})
    reports={}
    for league,(name,counts,blobs) in specs.items():
        rows=[]
        for season,n,blob in zip(("2022-23","2023-24","2024-25"),counts,blobs):
            a=load_season((root/season/name).read_bytes(),blob)
            if len(a)!=n: raise ValueError("incomplete season")
            rows.append(a)
        reports[league]=evaluate(*rows)
    return {"reports":reports,"retrospective_only":True,"prospective_verified":False,
            "confidence_interval_verified":False,"positive_ev_verified":False,"deployment":"HOLD","recommendations":"DISABLED"}

if __name__=="__main__":
    from argparse import ArgumentParser
    from json import dumps
    p=ArgumentParser();p.add_argument("root",type=Path)
    print(dumps(run(p.parse_args().root),indent=2))
