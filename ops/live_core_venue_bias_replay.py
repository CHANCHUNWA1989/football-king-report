"""Fixed venue-bias scenarios and train-only calibration; historical research."""
import json
import math
from collections import defaultdict
from datetime import date
from itertools import groupby
from urllib.request import Request,build_opener
from live_core_multi_source import blob,checked,row,unique,NoRedirect,LIMIT
from research_strict_json import unique_object,reject_constant
from live_core_walkforward_strength import clean,team_rates,OUTCOMES
from live_core_multi_league_stress import clip,update,paired_ci
from score_distribution_vnext import score_matrix,one_x_two

SEASONS=("2022-23","2023-24")
SPECS={
 "EPL":("en.1","English Premier League",380,("0b6230e60d8cd7402810a5f515f6762d8b385b74","f62b11dfaf06cffd1236c2777caebb880a0cfea1")),
 "BL":("de.1","Deutsche Bundesliga",306,("7fc779362c4d775bc7cea2fa3b79ce1941bbc796","2c41078e751d914f24bfe7e55c5567cea70a4aee")),
 "ES":("es.1","Primera División de España",380,("f777848f48f8ec0528cc0ec67c6c05bba0bca961","a9d391f61af872bb9f456951d2f71f10d9e10704"))}
MODELS=("baseline","away_shift_5","away_shift_10","train_venue_scale","train_venue_scale_dc")
def parse(raw,league,season):
    path,name,n,pins=SPECS[league]
    if blob(raw)!=pins[SEASONS.index(season)]:raise ValueError("BLOB_PIN_CHANGED")
    d=json.loads(checked(raw),object_pairs_hook=unique_object,parse_constant=reject_constant)
    if d["name"]!=name+" "+season.replace("-","/") or len(d["matches"])!=n:raise ValueError("LEAGUE_SCOPE")
    rows=unique([row(m["date"],m["team1"],m["team2"],m["score"]["ft"]) for m in d["matches"]])
    year=int(season[:4])
    if len(rows)!=n or any(not f"{year}-07-01"<=r[0]<f"{year+1}-07-01" for r in rows):raise ValueError("COHORT_SCOPE")
    return rows
def fetch(league,season):
    if season not in SEASONS or league not in SPECS:raise ValueError("SOURCE_SCOPE")
    url=f"https://raw.githubusercontent.com/openfootball/football.json/master/{season}/{SPECS[league][0]}.json"
    with build_opener(NoRedirect()).open(Request(url,headers={"User-Agent":"FootballKingResearch/1.0","Accept":"application/json"}),timeout=15) as res:
        if res.geturl()!=url or res.status!=200:raise ValueError("HTTP_SOURCE")
        raw=res.read(LIMIT+1)
    return parse(raw,league,season)

def raw_rates(rows):
    hist=defaultdict(lambda:[0.]*6)
    n=gh=ga=0
    for day,g in groupby(rows,key=lambda r:r[0]):
        batch=list(g)
        if n>=50:
            H,A=clip(gh/n),clip(ga/n)
            for _,home,away,x,y in batch:
                h,a=team_rates(hist[home],hist[away],H,A,8)
                yield (day,home,away,x,y,h,a)
        for _,home,away,x,y in batch:
            update(hist,home,away,x,y);n+=1;gh+=x;ga+=y

def fit(rows):
    # Fixed 50 pseudo-goals per side, capped scaling, training-only.
    obs=list(raw_rates(clean(rows)))
    if len(obs)<50:raise ValueError("INSUFFICIENT_CALIBRATION")
    scales=tuple(max(.85,min(1.15,(50+math.fsum(r[i] for r in obs))/(50+math.fsum(r[j] for r in obs)))) for i,j in ((3,5),(4,6)))
    return scales,len(obs)

def shift(h,a,f):
    # Transfer a fixed fraction of home goal rate toward away; preserve total
    # subject to legal rate bounds. No market data or observed test outcome.
    delta=min(h*f,h-.1,5.5-a)
    return h-delta,a+delta

def forecasts(train,test):
    train,test=clean(train),clean(test)
    if not train or not test or train[-1][0]>=test[0][0]:raise ValueError("TEMPORAL_SCOPE")
    scales,n=fit(train)
    obs=[]
    for day,home,away,x,y,h,a in raw_rates(train+test):
        if day<test[0][0]:continue
        sh,sa=clip(h*scales[0]),clip(a*scales[1])
        configs=((h,a,0),(*shift(h,a,.05),0),(*shift(h,a,.10),0),(sh,sa,0),(sh,sa,-.06))
        p={}
        for name,(hr,ar,rho) in zip(MODELS,configs):
            grid=score_matrix(hr,ar,rho=rho);v=one_x_two(grid)
            u=math.fsum(z for i,r in enumerate(grid) for j,z in enumerate(r) if i+j<=2)
            p[name]=(tuple(v[k] for k in OUTCOMES),u)
        obs.append((day,home,away,x,y,p))
    return scales,n,obs

def report(train,test):
    scales,n,rows=forecasts(train,test)
    metrics={};loss={}
    for name in MODELS:
        vals=[];groups=defaultdict(list)
        for day,_,_,x,y,ps in rows:
            p,u=ps[name];k=0 if x>y else 1 if x==y else 2
            ll=-math.log(max(p[k],1e-15))
            vals.append((ll,math.fsum((v-(i==k))**2 for i,v in enumerate(p)),(u-(x+y<=2))**2))
            groups[OUTCOMES[k]].append(ll)
        loss[name]=vals
        metrics[name]=dict(zip(("log_loss","brier","under25_brier"),(math.fsum(v[i] for v in vals)/len(vals) for i in range(3))))
        metrics[name]["by_actual_outcome"]={k:{"n":len(v),"log_loss":math.fsum(v)/len(v)} for k,v in sorted(groups.items())}
    for name in MODELS:
        weeks=defaultdict(list)
        for r,b,c in zip(rows,loss["baseline"],loss[name]):
            weeks[date.fromisoformat(r[0]).isocalendar()[:2]].append(b[0]-c[0])
        metrics[name]["baseline_minus_candidate_log_loss_ci95"]=paired_ci([(math.fsum(v),len(v)) for _,v in sorted(weeks.items())])
    return {"train_n":len(train),"calibration_n":n,"assessment_n":len(rows),
            "frozen_home_away_scales":list(scales),"models":metrics,"selected_model":None}

def run():
    return {"leagues":{k:report(*(fetch(k,s) for s in SEASONS)) for k in SPECS},
            "seasons":list(SEASONS),"train_only_scale_fit":True,"same_day_results_excluded":True,
            "historical_only":True,"independent_prospective_validation":False,
            "model_calibrated":False,"selected_model":None,"verified_forward_sample_credit":0,
            "positive_ev_verified":False,"production_recommendations":"DISABLED","status":"HOLD"}
if __name__=="__main__":
    print(json.dumps(run(),sort_keys=True,allow_nan=False))
