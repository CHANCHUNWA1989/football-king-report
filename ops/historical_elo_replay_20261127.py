"""Retrospective date-batched Davidson-Elo challenger, not live forecasts.
One prior season warmup per fold. Fixed research settings, no tuning.
"""
from collections import defaultdict
from itertools import groupby
from math import fsum
from pathlib import Path
from ops.historical_season_replay_20261127 import load_season,replay,_score,METRICS
from ops.historical_multileague_replay_20261127 import MANIFEST

K=20
HOME_ADV=65
INITIAL=1500
EARLIER={
    "EN":(380,"0b6230e60d8cd7402810a5f515f6762d8b385b74"),
    "DE":(306,"7fc779362c4d775bc7cea2fa3b79ce1941bbc796"),
    "FR":(380,"5fae7b79a038f09f1ae982143cdd02dc111eb9f5"),
}

def probabilities(home,away,nu):
    q=10**((home-away+HOME_ADV)/800)
    z=q+1/q+nu
    return q/z,nu/z,1/q/z

def _batch(rows,ratings,nu):
    """All fixtures on one calendar date see the same prior ratings."""
    delta=defaultdict(list)
    predictions=[]
    for day,h,a,f in rows:
        p=probabilities(ratings.get(h,INITIAL),ratings.get(a,INITIAL),nu)
        y=0 if f[0]>f[1] else 1 if f[0]==f[1] else 2
        predictions.append((day,p,y))
        change=K*((1,.5,0)[y]-(p[0]+.5*p[1]))
        delta[h].append(change)
        delta[a].append(-change)
    for t,changes in delta.items():
        ratings[t]=ratings.get(t,INITIAL)+fsum(changes)
    return predictions

def elo_replay(train,test):
    if not train or not test or max(x[0] for x in train)>=min(x[0] for x in test):
        raise ValueError("strict season separation required")
    draw_rate=sum(f[0]==f[1] for _,_,_,f in train)/len(train)
    if not 0<draw_rate<1:
        raise ValueError("unsupported training draw rate")
    nu=2*draw_rate/(1-draw_rate)
    ratings={}
    for _,rows in groupby(sorted(train,key=lambda x:x[0]),key=lambda x:x[0]):
        _batch(rows,ratings,nu)
    observed=[]
    for _,rows in groupby(sorted(test,key=lambda x:x[0]),key=lambda x:x[0]):
        observed.extend(_batch(rows,ratings,nu))
    losses=[_score(p,y) for _,p,y in observed]
    return {"test":len(test),"training_draw_rate":draw_rate,
            "metrics":{m:fsum(r[i] for r in losses)/len(test) for i,m in enumerate(METRICS)},
            "correct":sum(max(range(3),key=p.__getitem__)==y for _,p,y in observed),
            "date_batched":True,"retrospective_only":True}

def run(root):
    reports=[]
    for league,(name,n,sha1,sha2) in MANIFEST.items():
        n0,sha0=EARLIER[league]
        seasons=[]
        for season,count,blob in (("2022-23",n0,sha0),("2023-24",n,sha1),("2024-25",n,sha2)):
            rows=load_season((root/season/name).read_bytes(),blob)
            if len(rows)!=count:
                raise ValueError("incomplete season")
            seasons.append(rows)
        for i in range(2):
            static=replay(seasons[i],seasons[i+1])
            elo=elo_replay(seasons[i],seasons[i+1])
            reports.append({"league":league,"test_season":("2023-24","2024-25")[i],
                            "test":static["test"],"baseline":static["baseline"],
                            "static":static["challenger"],"elo":elo["metrics"],
                            "correct":static["correct"]+[elo["correct"]]})
    n=sum(r["test"] for r in reports)
    return {"reports":reports,"test":n,
            "metrics":{side:{m:fsum(r[side][m]*r["test"] for r in reports)/n for m in METRICS}
                       for side in ("baseline","static","elo")},
            "correct":[sum(r["correct"][i] for r in reports) for i in range(3)],
            "fixed_settings":{"K":K,"home_advantage":HOME_ADV,"initial":INITIAL},
            "retrospective_only":True,"prospective_verified":False,
            "confidence_interval_verified":False,"positive_ev_verified":False,
            "deployment":"HOLD","recommendations":"DISABLED"}

if __name__=="__main__":
    from argparse import ArgumentParser
    from json import dumps
    p=ArgumentParser()
    p.add_argument("root",type=Path)
    print(dumps(run(p.parse_args().root),indent=2))
