"""Causal calendar-day drift replay; fixed research settings, no tuning."""
from itertools import groupby
from math import fsum
from pathlib import Path
from ops.historical_season_replay_20261127 import load_season
from ops.historical_fair_model_replay_20261127 import TeamCounts
from ops.historical_opponent_adjusted_replay_20261127 import measures,METRICS

SEASONS=("2020-21","2021-22","2022-23","2023-24","2024-25")
MANIFEST={
    "EN":("en.1.json",380,("081509058af75c0c012d64e980dc4fa53720d933","5eadd9d91c71d45634f3969192ad908653681b23","0b6230e60d8cd7402810a5f515f6762d8b385b74","f62b11dfaf06cffd1236c2777caebb880a0cfea1","504f2e732fbc3c9caeb98e4382b13b094453b840")),
    "DE":("de.1.json",306,("39b187140dd0fe025e029d82dc40b5e59266678d","716c7bddd678bcac2cfc0988108a4196b1edda8e","7fc779362c4d775bc7cea2fa3b79ce1941bbc796","2c41078e751d914f24bfe7e55c5567cea70a4aee","9921b1d8485429913ff6d161500beb519d8b0e51")),
}
def update_scale(scale,n,actual,expected):
    if type(n) is not int or n<1 or expected<=0 or actual<0:
        raise ValueError("invalid batch")
    w=1-.98**n
    return max(.75,min(1.25,(1-w)*scale+w*actual/expected))

def replay(train,test):
    if not train or not test or max(r[0] for r in train)>=min(r[0] for r in test):
        raise ValueError("strict season separation required")
    pool=[fsum(r[3][i] for r in train)/len(train) for i in (0,1)]
    if min(pool)<=0: raise ValueError("invalid pool")
    counts=TeamCounts(pool);counts.update(train)
    scale=1.;lo=hi=scale;values=[[],[]];correct=[0,0]
    for _,batch in groupby(sorted(test,key=lambda r:r[0]),key=lambda r:r[0]):
        batch=list(batch);actual=[];expected=[]
        for _,h,a,f in batch:
            base=(pool[0]*counts.strength(h,0,1)*counts.strength(a,1,2),
                  pool[1]*counts.strength(a,1,1)*counts.strength(h,0,2))
            actual.append(sum(f));expected.append(sum(base))
            for i,mu in enumerate((base,tuple(v*scale for v in base))):
                v,c=measures(mu,f);values[i].append(v);correct[i]+=c
        scale=update_scale(scale,len(batch),fsum(actual),fsum(expected))
        lo=min(lo,scale);hi=max(hi,scale)
        counts.update(batch)
    return {"test":len(test),"end_scale":scale,"scale_range":[lo,hi],
            "metrics":[{m:fsum(v[i] for v in rs)/len(test) for i,m in enumerate(METRICS)} for rs in values],
            "correct":correct,"positive_ev_verified":False,"deployment":"HOLD","recommendations":"DISABLED"}

def run(root):
    reports=[]
    for league,(name,n,blobs) in MANIFEST.items():
        rows=[load_season((root/s/name).read_bytes(),b) for s,b in zip(SEASONS,blobs)]
        if any(len(r)!=n for r in rows): raise ValueError("incomplete source")
        for i in range(len(rows)-1):
            reports.append({"league":league,"season":SEASONS[i+1],**replay(rows[i],rows[i+1])})
    n=sum(r["test"] for r in reports)
    return {"reports":reports,"test":n,"combined":[{m:fsum(r["metrics"][i][m]*r["test"] for r in reports)/n for m in METRICS} for i in range(2)],
            "correct":[sum(r["correct"][i] for r in reports) for i in range(2)],
            "retrospective_only":True,"prospective_verified":False,"confidence_interval_verified":False,
            "positive_ev_verified":False,"deployment":"HOLD","recommendations":"DISABLED"}

if __name__=="__main__":
    from argparse import ArgumentParser
    from json import dumps
    p=ArgumentParser();p.add_argument("root",type=Path)
    print(dumps(run(p.parse_args().root),indent=2))
