"""Three-league fixed domestic fixture-density research; not measured fatigue."""
import json
import math
from collections import defaultdict, deque
from datetime import date
from itertools import groupby
from urllib.request import Request, build_opener
from live_core_multi_source import blob, checked, row, unique, NoRedirect, LIMIT
from research_strict_json import unique_object,reject_constant
from live_core_low_score_calibration import parse as parse_epl
from consolidated_historical_replay import fetch as fetch_epl
from live_core_two_league_elo import fetch_bl, report as elo_report
from live_core_walkforward_strength import clean, team_rates, OUTCOMES
from live_core_multi_league_stress import clip, update, paired_ci
from score_distribution_vnext import score_matrix, one_x_two

SEASONS=("2020-21","2021-22")
ES_PINS={"2020-21":"a75987a794ded50077d54d934a0bd951938becea",
         "2021-22":"0fc4da4c0d441eb9e1068b0dcd13495c54150882"}
MODELS=("baseline","short_rest_5pct","short_rest_10pct","dense_14d_5pct")

def parse_es(raw,season):
    if blob(raw)!=ES_PINS[season]:raise ValueError("BLOB_PIN_CHANGED")
    d=json.loads(checked(raw),object_pairs_hook=unique_object,parse_constant=reject_constant)
    if d["name"]!="Primera División de España "+season.replace("-","/") or len(d["matches"])!=380:
        raise ValueError("LEAGUE_SCOPE")
    rows=unique([row(m["date"],m["team1"],m["team2"],m["score"]["ft"]) for m in d["matches"]])
    year=int(season[:4])
    if len(rows)!=380 or any(not f"{year}-07-01"<=r[0]<f"{year+1}-07-01" for r in rows):
        raise ValueError("COHORT_SCOPE")
    return rows

def fetch_es(season):
    if season not in ES_PINS:raise ValueError("UNKNOWN_SEASON")
    url=f"https://raw.githubusercontent.com/openfootball/football.json/master/{season}/es.1.json"
    with build_opener(NoRedirect()).open(Request(url,headers={"User-Agent":"FootballKingResearch/1.0","Accept":"application/json"}),timeout=15) as res:
        if res.geturl()!=url or res.status!=200:raise ValueError("HTTP_SOURCE")
        raw=res.read(LIMIT+1)
    return parse_es(raw,season)

def features(prior,day):
    if prior and prior[-1]>=day:raise ValueError("NON_PRIOR_FIXTURE")
    while prior and (day-prior[0]).days>14:
        prior.popleft()
    rest=(day-prior[-1]).days if prior else None
    return rest,len(prior)

def adjust(h,a,hflag,aflag,penalty):
    # Fixed symmetric own attack penalty; no causal or medical interpretation.
    return clip(h*(1-penalty*int(hflag))),clip(a*(1-penalty*int(aflag)))

def forecasts(train,test):
    train,test=clean(train),clean(test)
    if len(train)<50 or not test or train[-1][0]>=test[0][0]:raise ValueError("TEMPORAL_SCOPE")
    boundary=test[0][0]
    hist=defaultdict(lambda:[0.]*6)
    schedule=defaultdict(deque)
    n=gh=ga=0
    obs=[]
    for day,g in groupby(train+test,key=lambda r:r[0]):
        batch=list(g);current=date.fromisoformat(day)
        if day>=boundary:
            H,A=clip(gh/n),clip(ga/n)
            for _,home,away,x,y in batch:
                h,a=team_rates(hist[home],hist[away],H,A,8)
                hr,hn=features(schedule[home],current)
                ar,an=features(schedule[away],current)
                hs,as_=hr is not None and hr<=3,ar is not None and ar<=3
                hd,ad=hn>=3,an>=3
                configs=((h,a),adjust(h,a,hs,as_,.05),adjust(h,a,hs,as_,.10),adjust(h,a,hd,ad,.05))
                pred={}
                for name,(r1,r2) in zip(MODELS,configs):
                    grid=score_matrix(r1,r2);p=one_x_two(grid)
                    u=math.fsum(v for i,r in enumerate(grid) for j,v in enumerate(r) if i+j<=2)
                    pred[name]=(tuple(p[k] for k in OUTCOMES),u)
                obs.append((day,home,away,x,y,(hr,ar,hn,an),pred))
        for _,home,away,x,y in batch:
            update(hist,home,away,x,y)
            n+=1;gh+=x;ga+=y
            for t in (home,away):schedule[t].append(current)
    return obs

def metrics(rows):
    out={"n":len(rows),"models":{}}
    if not rows:return out
    losses={}
    for name in MODELS:
        vals=[]
        for day,_,_,x,y,_,pred in rows:
            p,u=pred[name];k=0 if x>y else 1 if x==y else 2
            vals.append((-math.log(max(p[k],1e-15)),math.fsum((v-(i==k))**2 for i,v in enumerate(p)),(u-(x+y<=2))**2))
        losses[name]=vals
        out["models"][name]=dict(zip(("log_loss","brier","under25_brier"),(math.fsum(v[i] for v in vals)/len(vals) for i in range(3))))
    for name in MODELS:
        weeks=defaultdict(list)
        for row,b,c in zip(rows,losses["baseline"],losses[name]):
            weeks[date.fromisoformat(row[0]).isocalendar()[:2]].append(b[0]-c[0])
        out["models"][name]["baseline_minus_candidate_log_loss_ci95"]=paired_ci([(math.fsum(v),len(v)) for _,v in sorted(weeks.items())]) if len(rows)>=40 else None
    return out

def report(train,test):
    rows=forecasts(train,test)
    short=[r for r in rows if any(v is not None and v<=3 for v in r[5][:2])]
    dense=[r for r in rows if max(r[5][2:])>=3]
    return {"train_n":len(train),"all":metrics(rows),"short_rest_subset":metrics(short),
            "dense_14d_subset":metrics(dense),"unknown_rest_outside_14d_or_missing":sum(None in r[5][:2] for r in rows),
            "subsets_can_overlap":True,"selected_model":None}

def run():
    sources={"EPL":[parse_epl(fetch_epl(s),s) for s in SEASONS],
             "BL":[fetch_bl(s) for s in SEASONS],"ES":[fetch_es(s) for s in SEASONS]}
    return {"leagues":{k:report(*v) for k,v in sources.items()},
            "elo_replay":{k:elo_report(*v) for k,v in sources.items()},
            "historical_only":True,"domestic_league_dates_only":True,"all_competitions_rest_verified":False,
            "measured_player_fatigue":False,"lineup_or_xg_used":False,"same_day_results_excluded":True,
            "independent_prospective_validation":False,"selected_model":None,"verified_forward_sample_credit":0,
            "model_calibrated":False,"positive_ev_verified":False,"production_recommendations":"DISABLED","status":"HOLD"}

if __name__=="__main__":
    print(json.dumps(run(),sort_keys=True,allow_nan=False))
