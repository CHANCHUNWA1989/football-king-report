"""Retrospective recency-weighted Poisson on two new second-tier leagues."""
from collections import defaultdict
from itertools import groupby
from json import loads
from math import fsum
from pathlib import Path
from re import fullmatch
from ops.historical_season_replay_20261127 import load_season,_prob,_score,METRICS,SHRINK

HALVES=(0,90,180,365,730)  # zero means no decay
MANIFEST={
    "EN2":("en.2.json",557,552,("93450122b939ffba8488ef70d3879361b614c963","d74be22b7be265e1f8f96ae9906753815863a1d9","5feb65c819f9292005dcb1bffbdb4ca0a1cabb39")),
    "DE2":("de.2.json",306,306,("34f242df8a8e5ca1e895f083e2a565acd4d48141","e5cca55df7d571a5ee1a6ba1e3aaf521389c250a","6c95dd8c9cb480d76e03c670d744af65c2f09a33")),
}

class WeightedCounts:
    def __init__(self,pool,half):
        if half not in HALVES: raise ValueError("unsupported half-life")
        self.pool=pool;self.half=half;self.history=defaultdict(list)
    def update(self,rows):
        for day,h,a,f in rows:
            for i,t in enumerate((h,a)):
                self.history[t,i].append((day,f[i],f[1-i]))
    def strength(self,t,i,k,day):
        mu=self.pool[i if k==1 else 1-i]
        weights=[];values=[]
        for r in self.history.get((t,i),()):
            age=(day-r[0]).days
            if age<=0: raise ValueError("same-day or future feature")
            w=1 if self.half==0 else 2**(-age/self.half)
            weights.append(w);values.append(w*r[k])
        return (fsum(values)+SHRINK*mu)/(fsum(weights)+SHRINK)/mu
    def predict(self,day,h,a):
        return _prob((self.pool[0]*self.strength(h,0,1,day)*self.strength(a,1,2,day),
                      self.pool[1]*self.strength(a,1,1,day)*self.strength(h,0,2,day)))

def evaluate_rows(rows,counts):
    losses=[];correct=0
    for _,batch in groupby(sorted(rows,key=lambda r:r[0]),key=lambda r:r[0]):
        batch=list(batch)
        for day,h,a,f in batch:
            p=counts.predict(day,h,a)
            y=0 if f[0]>f[1] else 1 if f[0]==f[1] else 2
            losses.append(_score(p,y))
            correct+=int(max(range(3),key=p.__getitem__)==y)
        counts.update(batch)
    return {"metrics":{m:fsum(r[i] for r in losses)/len(rows) for i,m in enumerate(METRICS)},"correct":correct}

def replay(train,cal,test):
    if not train or not cal or not test or max(x[0] for x in train)>=min(x[0] for x in cal) or max(x[0] for x in cal)>=min(x[0] for x in test):
        raise ValueError("strict three-season separation required")
    pool=[fsum(r[3][i] for r in train)/len(train) for i in (0,1)]
    if min(pool)<=0: raise ValueError("invalid pool")
    states={};scores={}
    for h in HALVES:
        c=WeightedCounts(pool,h);c.update(train)
        scores[h]=evaluate_rows(cal,c)["metrics"]["log_loss"];states[h]=c
    selected=min(HALVES,key=scores.__getitem__)
    baseline=evaluate_rows(test,states[0])
    candidate=baseline if selected==0 else evaluate_rows(test,states[selected])
    return {"train":len(train),"cal":len(cal),"test":len(test),
            "selected_half_days":selected,"calibration_log_loss":scores,
            "baseline":baseline,"candidate":candidate,"retrospective_only":True,
            "prospective_verified":False,"positive_ev_verified":False,
            "deployment":"HOLD","recommendations":"DISABLED"}

def load_regular(raw,blob,raw_n,regular_n):
    rows=load_season(raw,blob)
    if len(rows)!=raw_n: raise ValueError("incomplete source")
    original=loads(raw)["matches"]
    regular=[r for r,x in zip(rows,original) if fullmatch(r"(Regular, )?Matchday \d+",x.get("round",""))]
    if len(regular)!=regular_n: raise ValueError("incomplete regular season")
    return regular

def run(root):
    reports={}
    for league,(name,raw_n,regular_n,blobs) in MANIFEST.items():
        rows=[load_regular((root/s/name).read_bytes(),blob,raw_n,regular_n)
              for s,blob in zip(("2022-23","2023-24","2024-25"),blobs)]
        reports[league]=replay(*rows)
    return {"reports":reports,"retrospective_only":True,"confidence_interval_verified":False,
            "prospective_verified":False,"positive_ev_verified":False,
            "deployment":"HOLD","recommendations":"DISABLED"}

if __name__=="__main__":
    from argparse import ArgumentParser
    from json import dumps
    p=ArgumentParser();p.add_argument("root",type=Path)
    print(dumps(run(p.parse_args().root),indent=2))
