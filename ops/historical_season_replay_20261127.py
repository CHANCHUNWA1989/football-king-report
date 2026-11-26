"""Retrospective season-separated 1X2 research; no odds or live model claims."""
from collections import defaultdict
from datetime import date
from hashlib import sha1
from json import loads
from math import exp, fsum, log

SHRINK=10
METRICS=("log_loss","brier","rps")

def load_season(raw, expected_blob):
    # Git blob identity, not independently authenticated source provenance.
    if not isinstance(raw,bytes) or not 0<len(raw)<=2_000_000:
        raise ValueError("invalid dataset size")
    blob=sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest()
    if blob!=expected_blob:
        raise ValueError("source blob mismatch")
    doc=loads(raw)
    rows=doc.get("matches") if isinstance(doc,dict) else None
    if not isinstance(rows,list) or not rows:
        raise ValueError("empty season")
    seen=set()
    out=[]
    for r in rows:
        if not isinstance(r,dict):
            raise ValueError("invalid fixture")
        day=date.fromisoformat(r["date"])
        h,a=r["team1"],r["team2"]
        if any(not isinstance(x,str) or not x.strip() for x in (h,a)) or h==a:
            raise ValueError("invalid team")
        key=(day,h,a)
        if key in seen:
            raise ValueError("duplicate fixture")
        seen.add(key)
        f=r.get("score",{}).get("ft")
        if not isinstance(f,list) or len(f)!=2 or any(type(x) is not int or not 0<=x<=30 for x in f):
            raise ValueError("missing or invalid full-time score")
        out.append((day,h,a,tuple(f)))
    return out

def _prob(mu):
    def poisson(m):
        if not 0<=m<=12:
            raise ValueError("unsupported rate")
        p=[exp(-m)]
        for k in range(1,81):
            p.append(p[-1]*m/k)
        return p
    h,a=map(poisson,mu)
    p=[[],[],[]]
    for i,x in enumerate(h):
        for j,y in enumerate(a):
            p[0 if i>j else 1 if i==j else 2].append(x*y)
    return [fsum(v) for v in p]

def _score(p,y):
    return (-log(max(p[y],1e-15)),fsum((v-(i==y))**2 for i,v in enumerate(p)),
            ((p[0]-(y==0))**2+(p[0]+p[1]-(y<=1))**2)/2)

def replay_pairs(train,test):
    if not train or not test or max(x[0] for x in train)>=min(x[0] for x in test):
        raise ValueError("strict season separation required")
    pool=[fsum(x[3][i] for x in train)/len(train) for i in (0,1)]
    if min(pool)<=0:
        raise ValueError("positive training rates required")
    teams=defaultdict(lambda:[[0,0],[0,0],[0,0]])
    for _,h,a,f in train:
        for i,t in enumerate((h,a)):
            z=teams[t];z[0][i]+=1;z[1][i]+=f[i];z[2][i]+=f[1-i]
    def strength(t,i,k):
        mu=pool[i if k==1 else 1-i]
        if t not in teams:
            return 1
        z=teams[t]
        return (z[k][i]+SHRINK*mu)/(z[0][i]+SHRINK)/mu
    base=_prob(pool)
    rows=[[],[]]
    correct=[0,0]
    unknown=0
    pairs=[]
    for day,h,a,f in test:
        unknown+=int(h not in teams or a not in teams)
        candidate=_prob((pool[0]*strength(h,0,1)*strength(a,1,2),
                         pool[1]*strength(a,1,1)*strength(h,0,2)))
        y=0 if f[0]>f[1] else 1 if f[0]==f[1] else 2
        for k,p in enumerate((base,candidate)):
            rows[k].append(_score(p,y))
            correct[k]+=int(max(range(3),key=p.__getitem__)==y)
        pairs.append((day,tuple(c-b for b,c in zip(rows[0][-1],rows[1][-1]))))
    means=[{m:fsum(r[i] for r in rs)/len(test) for i,m in enumerate(METRICS)} for rs in rows]
    report={"train":len(train),"test":len(test),"train_last":max(x[0] for x in train).isoformat(),
            "test_first":min(x[0] for x in test).isoformat(),"pool":pool,"unknown_team_fixtures":unknown,
            "baseline":means[0],"challenger":means[1],"delta":{m:means[1][m]-means[0][m] for m in METRICS},
            "correct":correct,"shrink_pseudomatches":SHRINK,"retrospective_only":True,
            "prospective_verified":False,"confidence_interval_verified":False,
            "positive_ev_verified":False,"deployment":"HOLD","recommendations":"DISABLED"}
    return report,pairs

def replay(train,test):
    return replay_pairs(train,test)[0]

if __name__=="__main__":
    from argparse import ArgumentParser
    from pathlib import Path
    from json import dumps
    p=ArgumentParser()
    p.add_argument("train");p.add_argument("test")
    p.add_argument("--train-blob",required=True);p.add_argument("--test-blob",required=True)
    args=p.parse_args()
    print(dumps(replay(load_season(Path(args.train).read_bytes(),args.train_blob),
                       load_season(Path(args.test).read_bytes(),args.test_blob)),indent=2))
