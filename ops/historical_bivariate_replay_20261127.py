"""Retrospective bivariate Poisson with nonnegative shared goal component."""
from math import fsum,log
from pathlib import Path
from ops.live_score_challenger_20261127 import poisson
from ops.historical_dc_replay_20261127 import EXTRA,dated_rates
from ops.historical_fair_model_replay_20261127 import TeamCounts
from ops.historical_recency_replay_20261127 import MANIFEST,load_regular
from ops.historical_season_replay_20261127 import load_season

SCALES=(.85,.9,.95,1,1.05,1.1,1.15)
SHARES=(0,.025,.05,.1,.15,.2)
METRICS=("exact","one_x_two","tail_p","tail_brier","margin_two_brier","tail_actual")

def components(mu,scale,share):
    if scale not in SCALES or share not in SHARES:
        raise ValueError("unsupported scenario")
    h,a=(v*scale for v in mu)
    if min(h,a)<0 or max(h,a)>12:
        raise ValueError("unsupported means")
    z=min(h,a)*share
    return poisson(h-z),poisson(a-z),poisson(z)

def exact_probability(parts,f):
    h,a,z=parts
    if len(f)!=2 or any(type(v) is not int or not 0<=v<=30 for v in f):
        raise ValueError("invalid score")
    return fsum(h[f[0]-k]*a[f[1]-k]*z[k] for k in range(min(f)+1))

def probabilities(parts):
    h,a,z=parts
    survival=[fsum(z[k:]) for k in range(4)]
    bins=[[],[],[]];tail=[];deep=[]
    for i,x in enumerate(h):
        for j,y in enumerate(a):
            v=x*y
            bins[0 if i>j else 1 if i==j else 2].append(v)
            if i-j>=2: deep.append(v)
            k=max(0,(6-i-j)//2)
            tail.append(v*survival[k])
    return [fsum(b) for b in bins],fsum(tail),fsum(deep)

def fit(rows,scales,shares):
    if not rows: raise ValueError("empty calibration")
    best=None
    for s in scales:
        for c in shares:
            v=-fsum(log(max(1e-15,exact_probability(components(mu,s,c),f))) for mu,f in rows)/len(rows)
            if best is None or v<best[2]-1e-12: best=(s,c,v)
    return best

def evaluate(rows,s,c):
    values=[];hits=0
    for mu,f in rows:
        parts=components(mu,s,c)
        p,t,deep=probabilities(parts)
        y=0 if f[0]>f[1] else 1 if f[0]==f[1] else 2
        actual=int(sum(f)>=5)
        values.append((-log(max(1e-15,exact_probability(parts,f))),-log(max(1e-15,p[y])),
                       t,(t-actual)**2,(deep-int(f[0]-f[1]>=2))**2,actual))
        hits+=int(max(range(3),key=p.__getitem__)==y)
    return {**{m:fsum(v[i] for v in values)/len(rows) for i,m in enumerate(METRICS)},"hits":hits}

def replay(train,cal,test):
    if not train or not cal or not test or max(r[0] for r in train)>=min(r[0] for r in cal) or max(r[0] for r in cal)>=min(r[0] for r in test):
        raise ValueError("strict three-season separation required")
    pool=[fsum(r[3][i] for r in train)/len(train) for i in (0,1)]
    if min(pool)<=0: raise ValueError("invalid pool")
    counts=TeamCounts(pool);counts.update(train)
    c=dated_rates(cal,counts)
    params={"baseline":(1,0,None),"scale":fit(c,SCALES,(0,)),
            "shared":fit(c,(1,),SHARES),"joint":fit(c,SCALES,SHARES)}
    rows=dated_rates(test,counts)
    return {"test":len(test),"params":params,"results":{k:evaluate(rows,*v[:2]) for k,v in params.items()},
            "deployment":"HOLD","recommendations":"DISABLED","positive_ev_verified":False}

def run(root):
    reports={};seasons=("2022-23","2023-24","2024-25")
    for league in ("NL","PT"):
        name,n,*blobs=EXTRA[league]
        rows=[load_season((root/s/name).read_bytes(),b) for s,b in zip(seasons,blobs)]
        if any(len(r)!=n for r in rows): raise ValueError("incomplete source")
        reports[league]=replay(*rows)
    for league,(name,raw_n,regular_n,blobs) in MANIFEST.items():
        reports[league]=replay(*[load_regular((root/s/name).read_bytes(),b,raw_n,regular_n)
                                for s,b in zip(seasons,blobs)])
    n=sum(r["test"] for r in reports.values())
    return {"reports":reports,"test":n,"combined":{k:{
        **{m:fsum(r["results"][k][m]*r["test"] for r in reports.values())/n for m in METRICS},
        "hits":sum(r["results"][k]["hits"] for r in reports.values())}
        for k in ("baseline","scale","shared","joint")},
        "retrospective_only":True,"prospective_verified":False,"actual_market_quotes":False,
        "confidence_interval_verified":False,"positive_ev_verified":False,
        "deployment":"HOLD","recommendations":"DISABLED"}

if __name__=="__main__":
    from argparse import ArgumentParser
    from json import dumps
    p=ArgumentParser();p.add_argument("root",type=Path)
    print(dumps(run(p.parse_args().root),indent=2))
