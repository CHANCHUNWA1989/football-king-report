"""Two-league fixed cross-season Elo and unseen-team research; never promote."""
import json
import math
from collections import defaultdict
from itertools import groupby
from urllib.request import Request, build_opener
from live_core_multi_source import blob, checked, row, unique, NoRedirect, LIMIT
from research_strict_json import unique_object, reject_constant
from live_core_low_score_calibration import parse as parse_epl
from consolidated_historical_replay import fetch as fetch_epl
from live_core_walkforward_strength import clean, team_rates, OUTCOMES
from live_core_multi_league_stress import clip, update
from score_distribution_vnext import score_matrix, one_x_two

BL_PINS={"2020-21":"39b187140dd0fe025e029d82dc40b5e59266678d",
         "2021-22":"716c7bddd678bcac2cfc0988108a4196b1edda8e"}
SEASONS=("2020-21","2021-22")
MODELS=("team_cumulative","elo_only","team_elo_blend","unseen_team_shrink")
K=20
HOME_ELO=65

def parse_bl(raw,season):
    if blob(raw)!=BL_PINS[season]:
        raise ValueError("BLOB_PIN_CHANGED")
    d=json.loads(checked(raw),object_pairs_hook=unique_object,parse_constant=reject_constant)
    if d["name"]!="Deutsche Bundesliga "+season.replace("-","/") or len(d["matches"])!=306:
        raise ValueError("LEAGUE_SCOPE")
    rows=unique([row(m["date"],m["team1"],m["team2"],m["score"]["ft"]) for m in d["matches"]])
    year=int(season[:4])
    if len(rows)!=306 or any(not f"{year}-07-01"<=r[0]<f"{year+1}-07-01" for r in rows):
        raise ValueError("COHORT_SCOPE")
    return rows

def fetch_bl(season):
    if season not in BL_PINS:
        raise ValueError("UNKNOWN_SEASON")
    url=f"https://raw.githubusercontent.com/openfootball/football.json/master/{season}/de.1.json"
    with build_opener(NoRedirect()).open(Request(url,headers={"User-Agent":"FootballKingResearch/1.0","Accept":"application/json"}),timeout=15) as res:
        if res.geturl()!=url or res.status!=200:
            raise ValueError("HTTP_SOURCE")
        raw=res.read(LIMIT+1)
    return parse_bl(raw,season)

def forecast(train,test):
    train,test=clean(train),clean(test)
    if len(train)<50 or not test or train[-1][0]>=test[0][0]:
        raise ValueError("TEMPORAL_SCOPE")
    seen={t for _,h,a,_,_ in train for t in (h,a)}
    boundary=test[0][0]
    hist=defaultdict(lambda:[0.]*6)
    elo=defaultdict(lambda:1500.)
    assessed_games=defaultdict(int)
    n=gh=ga=0
    obs=[]
    for day,g in groupby(train+test,key=lambda r:r[0]):
        batch=list(g)
        if day>=boundary:
            H,A=clip(gh/n),clip(ga/n)
            for _,home,away,x,y in batch:
                h,a=team_rates(hist[home],hist[away],H,A,8)
                gap=max(-400,min(400,elo[home]-elo[away]))/800
                eh,ea=clip(H*math.exp(gap)),clip(A*math.exp(-gap))
                cold=any(t not in seen and assessed_games[t]<5 for t in (home,away))
                ch,ca=team_rates(hist[home],hist[away],H,A,16) if cold else (h,a)
                configs=((h,a),(eh,ea),((h+eh)/2,(a+ea)/2),(ch,ca))
                pred={}
                for name,(hr,ar) in zip(MODELS,configs):
                    grid=score_matrix(hr,ar)
                    p=one_x_two(grid)
                    u=math.fsum(v for i,r in enumerate(grid) for j,v in enumerate(r) if i+j<=2)
                    pred[name]=(tuple(p[k] for k in OUTCOMES),u)
                obs.append((day,home,away,x,y,cold,pred))
        changes=defaultdict(float)
        for _,h,a,x,y in batch:
            # Frozen start-of-date ratings; no within-day result leakage.
            expected=1/(1+10**(-(elo[h]-elo[a]+HOME_ELO)/400))
            delta=K*((1 if x>y else .5 if x==y else 0)-expected)
            changes[h]+=delta;changes[a]-=delta
            update(hist,h,a,x,y)
            n+=1;gh+=x;ga+=y
            if day>=boundary:
                assessed_games[h]+=1;assessed_games[a]+=1
        for team,delta in changes.items():
            elo[team]+=delta
    return obs

def metrics(rows):
    if not rows:
        return {"n":0,"models":{}}
    result={}
    for name in MODELS:
        vals=[]
        for _,_,_,x,y,_,pred in rows:
            p,u=pred[name]
            k=0 if x>y else 1 if x==y else 2
            vals.append((-math.log(max(p[k],1e-15)),math.fsum((v-(i==k))**2 for i,v in enumerate(p)),(u-(x+y<=2))**2))
        result[name]=dict(zip(("log_loss","brier","under25_brier"),(math.fsum(v[i] for v in vals)/len(vals) for i in range(3))))
    return {"n":len(rows),"models":result}

def report(train,test):
    obs=forecast(train,test)
    cold=[r for r in obs if r[5]]
    warm=[r for r in obs if not r[5]]
    return {"train_n":len(train),"all":metrics(obs),"unseen_team_first_five":metrics(cold),
            "other":metrics(warm),"unseen_is_not_verified_promotion":True,
            "selected_model":None,"same_day_results_excluded":True}

def run():
    leagues={"EPL":report(*(parse_epl(fetch_epl(s),s) for s in SEASONS)),
             "BL":report(*(fetch_bl(s) for s in SEASONS))}
    return {"leagues":leagues,"fixed_elo_K":K,"fixed_home_elo":HOME_ELO,
            "historical_only":True,"independent_prospective_validation":False,
            "selected_model":None,"verified_forward_sample_credit":0,
            "model_calibrated":False,"positive_ev_verified":False,
            "production_recommendations":"DISABLED","status":"HOLD"}

if __name__=="__main__":
    print(json.dumps(run(),sort_keys=True,allow_nan=False))
