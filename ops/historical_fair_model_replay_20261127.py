"""Equal-information retrospective comparison. Fixed 50/50 mixture, not tuned."""
from collections import defaultdict
from itertools import groupby
from math import fsum
from pathlib import Path
from ops.historical_season_replay_20261127 import load_season,_prob,_score,METRICS,SHRINK
from ops.historical_elo_replay_20261127 import _batch,EARLIER
from ops.historical_multileague_replay_20261127 import MANIFEST

MODELS=("dynamic_poisson","elo","mixture")

class TeamCounts:
    def __init__(self,pool):
        self.pool=pool
        self.teams=defaultdict(lambda:[[0,0],[0,0],[0,0]])
    def strength(self,t,i,k):
        mu=self.pool[i if k==1 else 1-i]
        if t not in self.teams:
            return 1
        z=self.teams[t]
        return (z[k][i]+SHRINK*mu)/(z[0][i]+SHRINK)/mu
    def predict(self,h,a):
        return _prob((self.pool[0]*self.strength(h,0,1)*self.strength(a,1,2),
                      self.pool[1]*self.strength(a,1,1)*self.strength(h,0,2)))
    def update(self,rows):
        for _,h,a,f in rows:
            for i,t in enumerate((h,a)):
                z=self.teams[t];z[0][i]+=1;z[1][i]+=f[i];z[2][i]+=f[1-i]

def day_predictions(rows,counts,ratings,nu):
    rows=list(rows)
    # Read all Poisson predictions before admitting any same-day outcomes.
    pp=[counts.predict(h,a) for _,h,a,_ in rows]
    ee=_batch(rows,ratings,nu)
    counts.update(rows)
    return [(day,y,(p,e,tuple((x+z)/2 for x,z in zip(p,e))))
            for p,(day,e,y) in zip(pp,ee)]

def replay(train,test):
    if not train or not test or max(x[0] for x in train)>=min(x[0] for x in test):
        raise ValueError("strict season separation required")
    pool=[fsum(x[3][i] for x in train)/len(train) for i in (0,1)]
    d=sum(f[0]==f[1] for _,_,_,f in train)/len(train)
    if min(pool)<=0 or not 0<d<1:
        raise ValueError("unsupported training distribution")
    nu=2*d/(1-d)
    counts=TeamCounts(pool);ratings={}
    for _,rows in groupby(sorted(train,key=lambda x:x[0]),key=lambda x:x[0]):
        rows=list(rows);_batch(rows,ratings,nu);counts.update(rows)
    losses=[[],[],[]];correct=[0,0,0]
    for _,rows in groupby(sorted(test,key=lambda x:x[0]),key=lambda x:x[0]):
        for _,y,ps in day_predictions(rows,counts,ratings,nu):
            for i,p in enumerate(ps):
                losses[i].append(_score(p,y))
                correct[i]+=int(max(range(3),key=p.__getitem__)==y)
    return {"test":len(test),"metrics":{model:{m:fsum(r[j] for r in losses[i])/len(test)
             for j,m in enumerate(METRICS)} for i,model in enumerate(MODELS)},"correct":correct}

def run(root):
    reports=[]
    for league,(name,n,sha1,sha2) in MANIFEST.items():
        n0,sha0=EARLIER[league]
        seasons=[]
        for season,count,blob in (("2022-23",n0,sha0),("2023-24",n,sha1),("2024-25",n,sha2)):
            rows=load_season((root/season/name).read_bytes(),blob)
            if len(rows)!=count: raise ValueError("incomplete season")
            seasons.append(rows)
        for i in range(2):
            reports.append({"league":league,"season":("2023-24","2024-25")[i],
                            **replay(seasons[i],seasons[i+1])})
    n=sum(r["test"] for r in reports)
    return {"reports":reports,"test":n,
            "metrics":{side:{m:fsum(r["metrics"][side][m]*r["test"] for r in reports)/n
                       for m in METRICS} for side in MODELS},
            "correct":[sum(r["correct"][i] for r in reports) for i in range(3)],
            "mixture_weights":[.5,.5],"same_date_update_barrier":True,
            "retrospective_only":True,"prospective_verified":False,
            "confidence_interval_verified":False,"positive_ev_verified":False,
            "deployment":"HOLD","recommendations":"DISABLED"}

if __name__=="__main__":
    from argparse import ArgumentParser
    from json import dumps
    p=ArgumentParser();p.add_argument("root",type=Path)
    print(dumps(run(p.parse_args().root),indent=2))
