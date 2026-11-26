"""Unified score distribution fusion with chronological historical season holdouts.

Select one of fixed convex score-matrix mixtures on 2022/23 only. Freeze
weights for 2023/24 and previously inspected 2024/25; no live/EV promotion.
"""
import json
import math
from collections import defaultdict
from datetime import date
from itertools import groupby
from urllib.request import Request,build_opener
from live_core_multi_source import blob,checked,row,unique,NoRedirect,LIMIT
from research_strict_json import unique_object,reject_constant
from score_distribution_vnext import score_matrix,one_x_two,market_distribution,grade_score,validate_matrix
from live_core_multi_league_stress import rates,clip,update,paired_ci,MODELS,SPECS

PINS={
 ("EPL","2022-23"):"0b6230e60d8cd7402810a5f515f6762d8b385b74",
 ("EPL","2023-24"):"f62b11dfaf06cffd1236c2777caebb880a0cfea1",
 ("BL","2022-23"):"7fc779362c4d775bc7cea2fa3b79ce1941bbc796",
 ("BL","2023-24"):"2c41078e751d914f24bfe7e55c5567cea70a4aee",
 **{(k,"2024-25"):v[2] for k,v in SPECS.items()}}
WEIGHTS={
 "league":(1,0,0,0,0),"team":(0,1,0,0,0),"dc":(0,0,1,0,0),
 "elo":(0,0,0,1,0),"decay":(0,0,0,0,1),
 "equal":(.2,.2,.2,.2,.2),"team_elo":(0,.5,0,.5,0),
 "team_decay":(0,.5,0,0,.5),"dc_decay":(0,0,.5,0,.5),
 "balanced":(.1,.3,.1,.2,.3)}
OUTCOMES=("HOME","DRAW","AWAY")
GRADES=("FULL_WIN","HALF_WIN","PUSH","HALF_LOSS","FULL_LOSS")
LINES=(-.75,-.25,.25,.75)
EPOCH=date(1970,1,1)


def fetch(league,season):
    path,name,_,count=SPECS[league]
    pin=PINS[league,season]
    url=f"https://raw.githubusercontent.com/openfootball/football.json/master/{season}/{path}.json"
    with build_opener(NoRedirect()).open(Request(url,headers={"User-Agent":"FootballKingResearch/1.0","Accept":"application/json"}),timeout=15) as res:
        if res.geturl()!=url or res.status!=200:
            raise ValueError("HTTP_SOURCE")
        raw=res.read(LIMIT+1)
    if len(raw)>LIMIT or blob(raw)!=pin:
        raise ValueError("BLOB_CHANGED")
    d=json.loads(checked(raw),object_pairs_hook=unique_object,parse_constant=reject_constant)
    if d["name"]!=name.replace("2024/25",season.replace("-","/")):
        raise ValueError("LEAGUE_SCOPE")
    rows=unique([row(m["date"],m["team1"],m["team2"],m["score"]["ft"])
                 for m in d["matches"] if m.get("score",{}).get("ft") is not None])
    start=int(season[:4])
    if len(rows)!=count or any(not f"{start}-07-01"<=r[0]<f"{start+1}-07-01" for r in rows):
        raise ValueError("COHORT_SCOPE")
    return rows


def mix_grid(grids,weights):
    if len(grids)!=len(MODELS) or tuple(weights) not in WEIGHTS.values():
        raise ValueError("WEIGHT_CONTRACT")
    for g in grids:
        validate_matrix(g)
    h=max(map(len,grids)); a=max(len(g[0]) for g in grids)
    out=tuple(tuple(math.fsum(w*g[i][j] for w,g in zip(weights,grids)
        if i<len(g) and j<len(g[0])) for j in range(a)) for i in range(h))
    validate_matrix(out)
    return out


def projection(grid):
    p=one_x_two(grid)
    totals=[math.fsum(v for i,r in enumerate(grid) for j,v in enumerate(r)
                      if i+j<=line) for line in (1,2)]
    ah=[market_distribution(grid,market="asian_handicap",side="HOME",line=line)["outcome_probabilities"] for line in LINES]
    return tuple(p[k] for k in OUTCOMES)+tuple(totals)+tuple(v[k] for v in ah for k in GRADES)


def weighted_projection(vectors,weights):
    # Linear projection commutes with convex matrix mixture.
    return tuple(math.fsum(w*v[i] for w,v in zip(weights,vectors)) for i in range(len(vectors[0])))


def actual(x,y):
    k=0 if x>y else 1 if x==y else 2
    grades=[grade_score(x,y,market="asian_handicap",side="HOME",line=l) for l in LINES]
    return (k,int(x+y<=1),int(x+y<=2),tuple(GRADES.index(g) for g in grades))


def scores(p,y):
    k,l,u,grades=y
    loss=-math.log(max(1e-15,p[k]))
    b=math.fsum((p[i]-(i==k))**2 for i in range(3))
    b15=(p[3]-l)**2; b25=(p[4]-u)**2
    ah=math.fsum((p[5+5*j+i]-(i==g))**2
                 for j,g in enumerate(grades) for i in range(5))/len(LINES)
    # Prespecified proper scoring objective: 1X2 log loss + two market components.
    objective=loss+.25*(b15+b25)+.25*ah
    return (loss,b,int(max(range(3),key=lambda i:p[i])==k),b15,b25,ah,objective)


def observations(rows):
    hist=defaultdict(lambda:[0.]*6); decay=defaultdict(lambda:[0.]*6)
    elo=defaultdict(lambda:1500.)
    n=gh=ga=0;prev=None;obs=[]
    for day,g in groupby(unique(rows),key=lambda r:r[0]):
        batch=list(g);t=(date.fromisoformat(day)-EPOCH).days
        if prev is not None:
            factor=2**(-(t-prev)/90)
            for v in decay.values():
                for i in range(6):v[i]*=factor
        prev=t
        if n>=50:
            H,A=clip(gh/n),clip(ga/n)
            for _,home,away,x,y in batch:
                hr,ar=rates(hist[home],hist[away],H,A)
                dr,da=rates(decay[home],decay[away],H,A)
                gap=max(-400,min(400,elo[home]-elo[away]))/800
                configs=((H,A,0),(hr,ar,0),(hr,ar,-.08),
                         (clip(H*math.exp(gap)),clip(A*math.exp(-gap)),0),(dr,da,0))
                v=tuple(projection(score_matrix(h,a,rho=rho)) for h,a,rho in configs)
                obs.append(((t+3)//7,v,actual(x,y)))
        changes=defaultdict(float)
        for _,home,away,x,y in batch:
            update(hist,home,away,x,y);update(decay,home,away,x,y)
            expected=1/(1+10**(-(elo[home]-elo[away]+65)/400))
            delta=20*((1 if x>y else .5 if x==y else 0)-expected)
            changes[home]+=delta;changes[away]-=delta
            n+=1;gh+=x;ga+=y
        for team,delta in changes.items():elo[team]+=delta
    return obs


def assess(obs,name):
    if not obs:
        raise ValueError("EMPTY_ASSESSMENT")
    vals=[];weeks=defaultdict(list)
    for w,v,y in obs:
        s=scores(weighted_projection(v,WEIGHTS[name]),y)
        base=scores(v[0],y)
        vals.append(s);weeks[w].append(base[6]-s[6])
    keys=("log_loss","brier","accuracy","under15_brier","under25_brier","ah_grade_brier","objective")
    out=dict(zip(keys,(math.fsum(v[i] for v in vals)/len(vals) for i in range(len(keys)))))
    out["n"]=len(vals)
    out["baseline_minus_objective_ci95"]=paired_ci([(math.fsum(v),len(v)) for v in weeks.values()])
    return out


def select(obs):
    if len(obs)<100:
        raise ValueError("INSUFFICIENT_CALIBRATION")
    return min(WEIGHTS,key=lambda k:(assess(obs,k)["objective"],k))


def report():
    result={}
    for league in ("EPL","BL"):
        cal=observations(fetch(league,"2022-23"))
        selected=select(cal)
        out={"selected":selected,"weights":WEIGHTS[selected],"selection_n":len(cal),"seasons":{}}
        for season in ("2023-24","2024-25"):
            obs=observations(fetch(league,season))
            out["seasons"][season]={k:assess(obs,k) for k in dict.fromkeys(("league","team","elo","decay",selected))}
            out["seasons"][season]["frozen_selected"]=assess(obs,selected)
        result[league]=out
    mx=observations(fetch("MX","2024-25"))
    result["MX"]={"selected":None,"reason":"NO_SEPARATE_CALIBRATION_SEASON",
                  "descriptive_fixed_equal":assess(mx,"equal"),"baseline":assess(mx,"league")}
    return {"leagues":result,"historically_reconstructed":True,
            "assessment_independently_unseen_verified":False,
            "model_calibrated":False,"automatic_promotion":False,
            "positive_ev_verified":False,"verified_forward_sample_credit":0,
            "production_recommendations":"DISABLED","status":"HOLD"}


if __name__=="__main__":
    print(json.dumps(report(),sort_keys=True,allow_nan=False))
