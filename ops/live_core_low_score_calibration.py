"""Historical-only fixed-grid low-score calibration; no live or EV claims."""
import json
import math
from collections import defaultdict
from itertools import groupby
from urllib.request import Request,build_opener
from live_core_multi_source import blob,checked,row,unique,NoRedirect,LIMIT
from research_strict_json import unique_object,reject_constant
from live_core_multi_league_stress import clip,rates,update
from score_distribution_vnext import score_matrix,one_x_two

PINS={"2020-21":"081509058af75c0c012d64e980dc4fa53720d933",
      "2021-22":"5eadd9d91c71d45634f3969192ad908653681b23"}
GRID=tuple((s,r) for s in (.85,.95,1.,1.05,1.15) for r in (-.12,-.06,0.))
BASE=(1.,0.)


def parse(raw,season):
    if blob(raw)!=PINS[season]:raise ValueError("PIN_CHANGED")
    d=json.loads(checked(raw),object_pairs_hook=unique_object,parse_constant=reject_constant)
    if d["name"]!="English Premier League "+season.replace("-","/") or len(d["matches"])!=380:
        raise ValueError("SCOPE")
    rows=unique([row(m["date"],m["team1"],m["team2"],m["score"]["ft"]) for m in d["matches"]])
    start=int(season[:4])
    if len(rows)!=380 or any(not f"{start}-07-01"<=r[0]<f"{start+1}-07-01" for r in rows):
        raise ValueError("COHORT")
    return rows


def fetch(season):
    url=f"https://raw.githubusercontent.com/openfootball/football.json/master/{season}/en.1.json"
    with build_opener(NoRedirect()).open(Request(url,headers={"User-Agent":"FootballKingResearch/1.0","Accept":"application/json"}),timeout=15) as res:
        if res.geturl()!=url or res.status!=200:raise ValueError("HTTP_SOURCE")
        raw=res.read(LIMIT+1)
    if len(raw)>LIMIT:raise ValueError("SIZE_LIMIT")
    return parse(raw,season)


def observations(rows):
    hist=defaultdict(lambda:[0.]*6)
    n=gh=ga=0
    out=[]
    for day,g in groupby(unique(rows),key=lambda r:r[0]):
        batch=list(g)
        if n>=50:
            H,A=clip(gh/n),clip(ga/n)
            for _,h,a,x,y in batch:
                hr,ar=rates(hist[h],hist[a],H,A)
                out.append((hr,ar,x,y))
        for _,h,a,x,y in batch:
            update(hist,h,a,x,y)
            n+=1;gh+=x;ga+=y
    return out


def assess(obs,config):
    if config not in GRID or not obs:raise ValueError("ASSESSMENT")
    scale,rho=config
    scores=[]
    for hr,ar,x,y in obs:
        grid=score_matrix(clip(hr*scale),clip(ar*scale),rho=rho)
        p=one_x_two(grid)
        k="HOME" if x>y else "DRAW" if x==y else "AWAY"
        u1,u2=(math.fsum(v for i,r in enumerate(grid) for j,v in enumerate(r) if i+j<=line) for line in (1,2))
        ll=-math.log(max(1e-15,p[k]))
        b=math.fsum((v-(j==k))**2 for j,v in p.items())
        b1=(u1-(x+y<=1))**2;b2=(u2-(x+y<=2))**2
        scores.append((ll,b,b1,b2,ll+.25*(b1+b2)))
    return dict(zip(("log_loss","brier","under15_brier","under25_brier","objective"),
                    (math.fsum(v[i] for v in scores)/len(scores) for i in range(5))))


def select(train):
    if len(train)<100:raise ValueError("INSUFFICIENT_TRAIN")
    return min(GRID,key=lambda cfg:(assess(train,cfg)["objective"],cfg))


def report(train_rows,test_rows):
    if not train_rows or not test_rows or max(r[0] for r in train_rows)>=min(r[0] for r in test_rows):
        raise ValueError("TEMPORAL_OVERLAP")
    train=observations(train_rows)
    cfg=select(train)
    test=observations(test_rows)
    base=assess(test,BASE);candidate=assess(test,cfg)
    return {"train_n":len(train),"assessment_n":len(test),"grid_count":len(GRID),
            "selected_config":cfg,"baseline_config":BASE,"train_baseline":assess(train,BASE),
            "train_selected":assess(train,cfg),"assessment_baseline":base,"assessment_selected":candidate,
            "different_candidate":cfg!=BASE,"objective_improved":candidate["objective"]<base["objective"],
            "historical_only":True,"preregistered_independent_holdout":False,
            "model_calibrated":False,"automatic_promotion":False,"verified_forward_sample_credit":0,
            "positive_ev_verified":False,"production_recommendations":"DISABLED","status":"HOLD"}


if __name__=="__main__":
    print(json.dumps(report(fetch("2020-21"),fetch("2021-22")),sort_keys=True,allow_nan=False))
