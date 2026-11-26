"""Prior-date opponent-adjusted team strength; fixed historical diagnostics."""
import json
import math
from collections import defaultdict
from datetime import date
from itertools import groupby
from urllib.request import Request,build_opener
from live_core_multi_source import blob,checked,row,unique,NoRedirect,LIMIT
from research_strict_json import unique_object,reject_constant
from live_core_venue_bias_replay import fetch as fetch_prior
from live_core_walkforward_strength import clean,team_rates,OUTCOMES
from live_core_multi_league_stress import clip,update,paired_ci
from score_distribution_vnext import score_matrix,one_x_two

SPECS={
 "EPL":("en.1","English Premier League 2024/25",380,380,"504f2e732fbc3c9caeb98e4382b13b094453b840"),
 "BL":("de.1","Deutsche Bundesliga 2024/25",306,306,"9921b1d8485429913ff6d161500beb519d8b0e51"),
 "ES":("es.1","Spain Primera División 2024/25",380,370,"ba4e9bc10b172d6413a92aeba0c04eb70961cd05")}
MODELS=("baseline","opponent_adjusted","blend_25","blend_50")
def parse(raw,league):
    _,name,scheduled,finished,pin=SPECS[league]
    if blob(raw)!=pin:raise ValueError("BLOB_PIN_CHANGED")
    d=json.loads(checked(raw),object_pairs_hook=unique_object,parse_constant=reject_constant)
    if d["name"]!=name or len(d["matches"])!=scheduled:raise ValueError("LEAGUE_SCOPE")
    all_rows=unique([row(m["date"],m["team1"],m["team2"],m.get("score",{}).get("ft") if m.get("score",{}).get("ft") is not None else [0,0]) for m in d["matches"]])
    if len(all_rows)!=scheduled or any(not "2024-07-01"<=r[0]<"2025-07-01" for r in all_rows):
        raise ValueError("COHORT_SCOPE")
    # Placeholder scores above are used solely to validate fixture keys; never enter forecasts.
    rows=unique([row(m["date"],m["team1"],m["team2"],m["score"]["ft"]) for m in d["matches"] if m.get("score",{}).get("ft") is not None])
    if len(rows)!=finished:raise ValueError("FINISHED_SCOPE")
    return rows
def fetch(league):
    path=SPECS[league][0]
    url=f"https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/{path}.json"
    with build_opener(NoRedirect()).open(Request(url,headers={"User-Agent":"FootballKingResearch/1.0","Accept":"application/json"}),timeout=15) as res:
        if res.geturl()!=url or res.status!=200:raise ValueError("HTTP_SOURCE")
        raw=res.read(LIMIT+1)
    return parse(raw,league)

def factors(v):
    # Goal / opponent-adjusted expected exposure; eight pseudo-goals.
    return tuple(max(.4,min(2.5,(v[i]+8)/(v[i+1]+8))) for i in (0,2))
def adjusted(h,a,H,A):
    ha,hd=factors(h);aa,ad=factors(a)
    return clip(H*ha*ad),clip(A*aa*hd)

def forecasts(train,test):
    train,test=clean(train),clean(test)
    if len(train)<50 or not test or train[-1][0]>=test[0][0]:raise ValueError("TEMPORAL_SCOPE")
    hist=defaultdict(lambda:[0.]*6)
    adj=defaultdict(lambda:[0.]*4)
    n=gh=ga=0
    out=[]
    for day,g in groupby(train+test,key=lambda r:r[0]):
        batch=list(g)
        H,A=(clip(gh/n),clip(ga/n)) if n>=50 else (1.5,1.2)
        pending=[]
        for _,h,a,x,y in batch:
            ha,hd=factors(adj[h]);aa,ad=factors(adj[a])
            # Frozen opponent factors and league rates, not the full own forecast.
            pending.append((h,a,x,y,H*ad,A*aa,A*hd,H*ha))
            if day<test[0][0]:continue
            bh,ba=team_rates(hist[h],hist[a],H,A,8)
            oh,oa=adjusted(adj[h],adj[a],H,A)
            configs=((bh,ba),(oh,oa),(.75*bh+.25*oh,.75*ba+.25*oa),(.5*bh+.5*oh,.5*ba+.5*oa))
            preds={}
            for name,(hr,ar) in zip(MODELS,configs):
                grid=score_matrix(hr,ar);p=one_x_two(grid)
                u=math.fsum(v for i,r in enumerate(grid) for j,v in enumerate(r) if i+j<=2)
                preds[name]=(tuple(p[k] for k in OUTCOMES),u)
            gap=preds["baseline"][0][0]-preds["baseline"][0][2]
            band="home_favoured" if gap>=.20 else "away_favoured" if gap<=-.20 else "balanced"
            out.append((day,h,a,x,y,band,preds))
        for h,a,x,y,hexp,hcon,aexp,acon in pending:
            # Update only after every prediction on this date.
            for team,goals,exposure,conceded,conex in ((h,x,hexp,y,hcon),(a,y,aexp,x,acon)):
                v=adj[team];v[0]+=goals;v[1]+=exposure;v[2]+=conceded;v[3]+=conex
            update(hist,h,a,x,y);n+=1;gh+=x;ga+=y
    return out

def metrics(rows):
    out={"n":len(rows),"models":{}}
    if not rows:return out
    losses={}
    for name in MODELS:
        vals=[]
        for day,_,_,x,y,_,preds in rows:
            p,u=preds[name];k=0 if x>y else 1 if x==y else 2
            vals.append((-math.log(max(p[k],1e-15)),math.fsum((v-(i==k))**2 for i,v in enumerate(p)),(u-(x+y<=2))**2))
        losses[name]=vals
        out["models"][name]=dict(zip(("log_loss","brier","under25_brier"),(math.fsum(v[i] for v in vals)/len(vals) for i in range(3))))
    for name in MODELS:
        weeks=defaultdict(list)
        for r,b,c in zip(rows,losses["baseline"],losses[name]):
            weeks[date.fromisoformat(r[0]).isocalendar()[:2]].append(b[0]-c[0])
        out["models"][name]["baseline_minus_candidate_log_loss_ci95"]=paired_ci([(math.fsum(v),len(v)) for _,v in sorted(weeks.items())]) if len(rows)>=40 else None
    return out
def report(train,test):
    rows=forecasts(train,test)
    bands={k:metrics([r for r in rows if r[5]==k]) for k in ("home_favoured","balanced","away_favoured")}
    return {"train_n":len(train),"assessment":metrics(rows),"baseline_pre_match_bands":bands,"selected_model":None}
def run():
    leagues={}
    for k,(_,_,scheduled,finished,_) in SPECS.items():
        leagues[k]={**report(fetch_prior(k,"2023-24"),fetch(k)),
                    "scheduled_assessment":scheduled,"missing_final_score":scheduled-finished}
    return {"leagues":leagues,"prior_date_only":True,"fixed_model_weights":True,
            "missing_matches_not_imputed":True,"historical_only":True,
            "independent_prospective_validation":False,"selected_model":None,"verified_forward_sample_credit":0,
            "model_calibrated":False,"positive_ev_verified":False,"production_recommendations":"DISABLED","status":"HOLD"}
if __name__=="__main__":
    print(json.dumps(run(),sort_keys=True,allow_nan=False))
