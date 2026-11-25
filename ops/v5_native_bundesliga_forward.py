"""V5 seven-model native-ID Bundesliga forward research.
Only authorized OpenLigaDB season snapshots. No authenticated outcomes or bets.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler
from zoneinfo import ZoneInfo
import importlib.util

MODEL="v5-seven-model-native-bundesliga-shadow-v1"
HK=ZoneInfo("Asia/Hong_Kong")
BERLIN=ZoneInfo("Europe/Berlin")
URL="https://api.openligadb.de/getmatchdata/"
SCOPES={"bl1":("bundesliga",18),"bl2":("bundesliga2",18),"bl3":("germany_liga3",20)}

def scope(shortcut):
    if shortcut not in SCOPES:raise ValueError("UNSUPPORTED_LEAGUE")
    return SCOPES[shortcut]
LIMIT=3_000_000
NAMES=("joint_poisson","dixon_coles","dynamic_elo","logistic","lightgbm","catboost","xgboost")
WEIGHTS={k:.5 if k=="joint_poisson" else 1/12 for k in NAMES}

def utc(s):
    if not isinstance(s,str):raise ValueError("INVALID_TIMESTAMP")
    d=datetime.fromisoformat(s.replace("Z","+00:00"))
    if d.utcoffset() is None:raise ValueError("NAIVE_TIMESTAMP")
    return d.astimezone(timezone.utc)

def native(v):
    if type(v) is not int or not 0<v<2**63:raise ValueError("BAD_NATIVE_ID")
    return str(v)

def decode(raw):
    def pairs(items):
        d={}
        for k,v in items:
            if k in d:raise ValueError("DUPLICATE_JSON_KEY")
            d[k]=v
        return d
    def invalid(_):raise ValueError("NONFINITE_JSON")
    if not 0<len(raw)<=LIMIT:raise ValueError("SIZE_LIMIT")
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)

def normalize(payload,season,now,*,previous=False,shortcut="bl1"):
    _,team_count=scope(shortcut)
    if not isinstance(payload,list) or not 1<=len(payload)<=400:
        raise ValueError("INVALID_SEASON_SIZE")
    ids=set();pairs=set();names={};finished=[];fixtures=[];league_ids=set()
    cutoff=now.astimezone(HK).date()
    for r in payload:
        if not isinstance(r,dict) or r.get("leagueShortcut")!=shortcut or type(r.get("leagueSeason")) is not int or r["leagueSeason"]!=season:
            raise ValueError("WRONG_SEASON_OR_LEAGUE")
        league_ids.add(native(r["leagueId"]))
        mid=native(r["matchID"]);h=native(r["team1"]["teamId"]);a=native(r["team2"]["teamId"])
        if mid in ids or h==a or (h,a) in pairs:raise ValueError("DUPLICATE_FIXTURE")
        ids.add(mid);pairs.add((h,a))
        for tid,team in ((h,r["team1"]),(a,r["team2"])):
            label=team["teamName"]
            if not isinstance(label,str) or not 0<len(label.strip())<=109:raise ValueError("BAD_TEAM_LABEL")
            if tid in names and names[tid]!=label:raise ValueError("TEAM_LABEL_CONFLICT")
            names[tid]=label
        ko=utc(r["matchDateTimeUTC"])
        if not datetime(season,7,1,tzinfo=timezone.utc)<=ko<datetime(season+1,7,1,tzinfo=timezone.utc):
            raise ValueError("DATE_OUTSIDE_SEASON")
        done=r.get("matchIsFinished")
        if type(done) is not bool:raise ValueError("UNKNOWN_MATCH_STATE")
        result=r.get("matchResults")
        if not isinstance(result,list):raise ValueError("BAD_RESULT_LIST")
        day=ko.astimezone(HK).date()
        if done:
            if ko+timedelta(hours=2)>now:raise ValueError("PREMATURE_FINAL_SCORE")
            ft=[x for x in result if isinstance(x,dict) and x.get("resultTypeID")==2]
            if len(ft)!=1:raise ValueError("MISSING_OR_AMBIGUOUS_FT")
            score=[ft[0]["pointsTeam1"],ft[0]["pointsTeam2"]]
            if any(type(x) is not int or not 0<=x<=20 for x in score):raise ValueError("BAD_SCORE")
            if day<cutoff:finished.append({"date":day.isoformat(),"team1":h,"team2":a,"score":score})
        elif previous:
            raise ValueError("INCOMPLETE_PREVIOUS_SEASON")
        elif not result and now+timedelta(minutes=10)<ko<=now+timedelta(days=7):
            fixtures.append({"event_id":mid,"h":h,"a":a,"kickoff_utc":ko.isoformat()})
    if len(league_ids)!=1:raise ValueError("AMBIGUOUS_LEAGUE_ID")
    if previous and (len(finished)!=team_count*(team_count-1) or len(names)!=team_count):raise ValueError("INCOMPLETE_TRAINING_SEASON")
    if len(names)>team_count:raise ValueError("TOO_MANY_NATIVE_TEAMS")
    return {"history":{"matches":finished},"fixtures":fixtures,"names":names,"ids":ids}

def state(rows,elo):
    groups=defaultdict(list)
    for r in rows:groups[r[0]].append(r)
    ratings={};teams=defaultdict(list);prior=[]
    for day in sorted(groups):
        changes=defaultdict(float)
        for _,h,a,x,y in groups[day]:
            expected=1/(1+10**((ratings.get(a,1500.)-ratings.get(h,1500.)-elo.HOME_ELO)/400))
            delta=elo.K*((1 if x>y else .5 if x==y else 0)-expected)
            changes[h]+=delta;changes[a]-=delta
            teams[h].append((x,y,3 if x>y else 1 if x==y else 0))
            teams[a].append((y,x,3 if y>x else 1 if y==x else 0))
            prior.append((x,y))
        for team,d in changes.items():ratings[team]=ratings.get(team,1500.)+d
    return ratings,teams,prior

def feature(teams,prior,h,a,ml):
    H,A=teams.get(h,[]),teams.get(a,[])
    if len(prior)<ml.MIN_HISTORY or min(len(H),len(A))<ml.MIN_TEAM:return None
    def avg(v,i):return sum(x[i] for x in v)/len(v)
    return [avg(prior,0),avg(prior,1),avg(H,0),avg(H,1),avg(A,0),avg(A,1),
            avg(H,2),avg(A,2),len(H),len(A),avg(H[-5:],2),avg(A[-5:],2)]

def run(old,new,now,joint,elo,ml,ensemble,*,shortcut="bl1"):
    season=now.astimezone(BERLIN).year-int(now.astimezone(BERLIN).month<7)
    p=normalize(old,season-1,now,previous=True,shortcut=shortcut);c=normalize(new,season,now,shortcut=shortcut)
    if p["ids"]&c["ids"]:raise ValueError("CROSS_SEASON_DUPLICATE_ID")
    previous=joint.parse(p["history"]);current=joint.parse(c["history"])
    if len(current)<ml.MIN_HISTORY:raise ValueError("INSUFFICIENT_CURRENT_HISTORY")
    if max(r[0] for r in previous)>=min(r[0] for r in current):raise ValueError("OVERLAPPING_SEASONS")
    jm=joint.fit(previous,min(r[0] for r in current))
    training=ml.features(p["history"])
    y=[r["y"] for r in training]
    if len(training)<100 or set(y)!={0,1,2}:raise ValueError("INSUFFICIENT_ML_TRAIN")
    models={}
    for k in ml.BACKENDS:
        m=ml.classifier(k);m.fit([r["x"] for r in training],y)
        if list(m.classes_)!=[0,1,2]:raise ValueError("BAD_CLASS_ORDER")
        models[k]=m
    ratings,teams,prior=state(current,elo)
    cutoff=now.astimezone(HK).date()
    result=[];excluded=defaultdict(int)
    for f in c["fixtures"]:
        h,a=f["h"],f["a"]
        jr=joint.rates(jm,h,a);er=elo.rates(current,cutoff,h,a,ratings,True);x=feature(teams,prior,h,a,ml)
        if jr is None or er is None or x is None or any(not .05<=v<=8 for v in jr):
            excluded["INSUFFICIENT_OR_UNSEEN_TEAM"]+=1;continue
        v={"joint_poisson":ensemble.vec(joint.probability(jr)),
           "dixon_coles":ensemble.dc(*jr),"dynamic_elo":ensemble.vec(elo.probabilities(*er))}
        for k,m in models.items():v[k]=ensemble.vec([float(z) for z in m.predict_proba([x])[0]])
        result.append({"provider_event_id":f["event_id"],"home_native_id":h,"away_native_id":a,
            "home":c["names"][h],"away":c["names"][a],"kickoff_utc":f["kickoff_utc"],
            "p_1x2":ensemble.blend(v,WEIGHTS),"model_probabilities":v,
            "joint_goal_rates":list(jr),"joint_rates_are_not_ensemble_goal_distribution":True,
            "production_recommendations":"DISABLED"})
    return {"season":season,"previous_finished":len(previous),"current_finished":len(current),
        "ml_training_n":len(training),"scheduled_in_window":len(c["fixtures"]),
        "exclusions":dict(excluded),"predictions":result}

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*a,**k):raise ValueError("REDIRECT_REFUSED")

def fetch(season,shortcut="bl1"):
    scope(shortcut)
    url=URL+shortcut+"/"+str(season)
    with build_opener(NoRedirect()).open(Request(url,headers={"User-Agent":"FootballKingResearch/5.0","Accept":"application/json"}),timeout=15) as response:
        raw=response.read(LIMIT+1)
    payload=decode(raw)
    return payload,{"source":url,"captured_utc":datetime.now(timezone.utc).isoformat(),"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)}

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
    p=argparse.ArgumentParser()
    for k in ("joint","elo","ml","ensemble","output"):p.add_argument("--"+k,required=True)
    p.add_argument("--league",choices=tuple(SCOPES),default="bl1")
    a=p.parse_args()
    league,_=scope(a.league)
    start=datetime.now(timezone.utc);local=start.astimezone(BERLIN)
    season=local.year-int(local.month<7)
    report={"schema":"v5-native-forward-shadow-v1","model_id":MODEL if a.league=="bl1" else "v5-1-seven-model-native-"+a.league+"-shadow-v1","league":league,
        "provider_league_shortcut":a.league,"league_weight_transfer_unvalidated":a.league!="bl1",
        "status":"HOLD","predictions":[],"weights":WEIGHTS,
        "provider":"OpenLigaDB","source_independent":False,"result_authentication":False,
        "external_capture_witness_verified":False,"verified_forward_sample_credit":0,
        "feature_availability_independently_verified":False,"market_odds_available":False,
        "production_recommendations":"DISABLED","automatic_promotion":False,
        "source_license":"ODbL 1.0; OpenLigaDB/community contributors https://www.openligadb.de/"}
    try:
        old,r1=fetch(season-1,a.league);new,r2=fetch(season,a.league)
        report["source_receipts"]=[r1,r2]
        now=datetime.now(timezone.utc)
        if start.astimezone(HK).date()!=now.astimezone(HK).date():raise ValueError("CUTOFF_DAY_CHANGED")
        result=run(old,new,now,*[load(getattr(a,k),k) for k in ("joint","elo","ml","ensemble")],shortcut=a.league)
        end=datetime.now(timezone.utc)
        if not start<=now<=end<=start+timedelta(minutes=10) or end.astimezone(HK).date()!=now.astimezone(HK).date():
            raise ValueError("INVALID_COMPLETION_CLOCK")
        rows=[r for r in result["predictions"] if utc(r["kickoff_utc"])>end+timedelta(minutes=10)]
        for r in rows:r["prediction_utc"]=end.isoformat()
        report.update(result);report["predictions"]=rows
        report["completion_excluded"]=len(result["predictions"])-len(rows)
        report["status"]="SHADOW_ONLY" if rows else "HOLD"
    except (OSError,ValueError,TypeError,KeyError,AttributeError,ImportError,OverflowError) as e:
        report["reason"]=type(e).__name__+":"+str(e)[:120] if isinstance(e,ValueError) else type(e).__name__
    report["generated_utc"]=datetime.now(timezone.utc).isoformat()
    report["predictions_count"]=len(report["predictions"])
    with Path(a.output).open("x",encoding="utf-8") as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in report.items() if k!="predictions"},allow_nan=False))
if __name__=="__main__":main()
