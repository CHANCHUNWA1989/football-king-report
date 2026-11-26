"""Research-only opponent-adjusted Poisson attack/defence replay."""
from collections import defaultdict
from itertools import groupby
from math import fsum,log
from pathlib import Path
from ops.historical_season_replay_20261127 import load_season
from ops.historical_fair_model_replay_20261127 import TeamCounts
from ops.live_score_challenger_20261127 import score_grid

MANIFEST={
    "EN":("en.1.json",380,"081509058af75c0c012d64e980dc4fa53720d933","5eadd9d91c71d45634f3969192ad908653681b23"),
    "DE":("de.1.json",306,"39b187140dd0fe025e029d82dc40b5e59266678d","716c7bddd678bcac2cfc0988108a4196b1edda8e"),
    "NL":("nl.1.json",306,"664fe96cfb1fee5ec3d3d650e09a083d0f55b669","ba34361d66cebf79425394f196cb815a09adf179"),
    "PT":("pt.1.json",306,"6449f91ba046d9596da8ad9bb7ed5f7dca7d97f8","bb52c47db1f26e4425973e9a756b70f88c3581ab"),
    "FR":("fr.1.json",380,"f7fecceedcfc367bc252caf2de2bab0fd7fc95f4","eff96e594a2651be60e09555a5f70aacf2be4716"),
}
METRICS=("one_x_two","exact","brier","tail_p","tail_brier","tail_actual")

def fit(edges,mu,direction):
    # Penalized likelihood: each multiplicative factor has penalty
    # 10*mu*(log(factor)-factor), mode at neutral strength.
    if mu<=0 or direction not in (0,1): raise ValueError("invalid fit")
    rows=[(h if direction==0 else a,a if direction==0 else h,n,g[direction])
          for (h,a),(n,g) in edges.items()]
    by_a=defaultdict(list);by_d=defaultdict(list)
    for a,d,n,g in rows:
        by_a[a].append((d,n,g));by_d[d].append((a,n,g))
    A=dict.fromkeys(by_a,1.0);D=dict.fromkeys(by_d,1.0)
    prior=10*mu
    for it in range(1,151):
        change=0
        for groups,x,y in ((by_a,A,D),(by_d,D,A)):
            for t,rs in groups.items():
                value=(prior+fsum(g for _,_,g in rs))/(prior+mu*fsum(n*y[o] for o,n,_ in rs))
                change=max(change,abs(log(value/x[t])))
                x[t]=value
        if change<1e-9: return A,D,it
    raise ArithmeticError("coordinate convergence not reached")

def measures(mu,f):
    g=score_grid((0,0),*mu)
    p=[fsum(v for (h,a),v in g.items() if (0 if h>a else 1 if h==a else 2)==i) for i in range(3)]
    y=0 if f[0]>f[1] else 1 if f[0]==f[1] else 2
    tail=fsum(v for (h,a),v in g.items() if h+a>=5)
    actual=int(sum(f)>=5)
    return (-log(max(1e-15,p[y])),-log(max(1e-15,g.get(f,0))),
            fsum((v-(i==y))**2 for i,v in enumerate(p)),tail,(tail-actual)**2,actual),int(max(range(3),key=p.__getitem__)==y)

def replay(train,test):
    if not train or not test or max(r[0] for r in train)>=min(r[0] for r in test):
        raise ValueError("strict season separation required")
    pool=[fsum(r[3][i] for r in train)/len(train) for i in (0,1)]
    if min(pool)<=0: raise ValueError("invalid pool")
    counts=TeamCounts(pool);edges={}
    def update(rows):
        counts.update(rows)
        for _,h,a,f in rows:
            n,g=edges.get((h,a),(0,[0,0]))
            edges[h,a]=(n+1,[g[i]+f[i] for i in (0,1)])
    update(train)
    values=[[],[]];hits=[0,0];max_iter=0
    for _,batch in groupby(sorted(test,key=lambda r:r[0]),key=lambda r:r[0]):
        batch=list(batch)
        A,D,it=fit(edges,pool[0],0);B,E,jt=fit(edges,pool[1],1)
        max_iter=max(max_iter,it,jt)
        for _,h,a,f in batch:
            base=(pool[0]*counts.strength(h,0,1)*counts.strength(a,1,2),
                  pool[1]*counts.strength(a,1,1)*counts.strength(h,0,2))
            joint=(pool[0]*A.get(h,1)*D.get(a,1),pool[1]*B.get(a,1)*E.get(h,1))
            for k,mu in enumerate((base,joint)):
                v,c=measures(mu,f);values[k].append(v);hits[k]+=c
        update(batch)
    return {"train":len(train),"test":len(test),"max_iter":max_iter,
            "metrics":[{m:fsum(v[i] for v in rs)/len(test) for i,m in enumerate(METRICS)} for rs in values],
            "correct":hits,"positive_ev_verified":False,"deployment":"HOLD","recommendations":"DISABLED"}

def run(root):
    reports={}
    for league,(name,n,s0,s1) in MANIFEST.items():
        rows=[load_season((root/s/name).read_bytes(),b) for s,b in zip(("2020-21","2021-22"),(s0,s1))]
        if any(len(r)!=n for r in rows): raise ValueError("incomplete source")
        reports[league]=replay(*rows)
    n=sum(r["test"] for r in reports.values())
    return {"reports":reports,"test":n,"combined":[{m:fsum(r["metrics"][i][m]*r["test"] for r in reports.values())/n for m in METRICS} for i in range(2)],
            "correct":[sum(r["correct"][i] for r in reports.values()) for i in range(2)],
            "retrospective_only":True,"prospective_verified":False,"confidence_interval_verified":False,
            "positive_ev_verified":False,"deployment":"HOLD","recommendations":"DISABLED"}

if __name__=="__main__":
    from argparse import ArgumentParser
    from json import dumps
    p=ArgumentParser();p.add_argument("root",type=Path)
    print(dumps(run(p.parse_args().root),indent=2))
