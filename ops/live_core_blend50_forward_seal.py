"""Locked forward research capture. Local integrity, NOT external attestation.

No network, no credentials, no bets. Input metadata is supplied by caller;
two distinct provider labels are not proof of source independence.
"""
import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime,timedelta,timezone,date
from itertools import groupby
from pathlib import Path
from live_core_opponent_strength import factors,adjusted
from live_core_walkforward_strength import team_rates,OUTCOMES,clean
from live_core_multi_league_stress import clip,update
from score_distribution_vnext import score_matrix,one_x_two
from research_strict_json import unique_object,reject_constant

PROTOCOL="FK-BLEND50-FORWARD-RESEARCH-2026-12-V1"
START=datetime(2026,12,1,tzinfo=timezone.utc)
END=datetime(2027,3,1,tzinfo=timezone.utc)
HISTORY_START=date(2025,7,1)
LEAGUES=("EPL","BL","ES")
MAX_BYTES=4_000_000
MAX_HISTORY=2000

def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")
def digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()
def instant(s):
    if type(s) is not str:raise ValueError("CLOCK")
    t=datetime.fromisoformat(s.replace("Z","+00:00"))
    if t.tzinfo is None:raise ValueError("NAIVE_CLOCK")
    return t.astimezone(timezone.utc)
def fields(doc,keys):
    if type(doc) is not dict or set(doc)!=set(keys.split()):raise ValueError("FIELD_SCOPE")
def identifier(v):
    if type(v) is not str or not 1<=len(v)<=160 or v!=v.strip() or any(ord(c)<32 for c in v):
        raise ValueError("IDENTIFIER")
    return v

def prior_rates(rows,home,away):
    # Exact prior-date update rule of the historical opponent-strength model.
    rows=clean(rows)
    if len(rows)<50:raise ValueError("INSUFFICIENT_HISTORY")
    hist=defaultdict(lambda:[0.]*6);adj=defaultdict(lambda:[0.]*4)
    n=gh=ga=0
    for _,group in groupby(rows,key=lambda r:r[0]):
        batch=list(group)
        H,A=(clip(gh/n),clip(ga/n)) if n>=50 else (1.5,1.2)
        pending=[]
        for _,h,a,x,y in batch:
            ha,hd=factors(adj[h]);aa,ad=factors(adj[a])
            pending.append((h,a,x,y,H*ad,A*aa,A*hd,H*ha))
        for h,a,x,y,hexp,hcon,aexp,acon in pending:
            for team,goals,exposure,conceded,conex in ((h,x,hexp,y,hcon),(a,y,aexp,x,acon)):
                v=adj[team];v[0]+=goals;v[1]+=exposure;v[2]+=conceded;v[3]+=conex
            update(hist,h,a,x,y);n+=1;gh+=x;ga+=y
    H,A=clip(gh/n),clip(ga/n)
    bh,ba=team_rates(hist[home],hist[away],H,A,8)
    oh,oa=adjusted(adj[home],adj[away],H,A)
    return {"baseline":(bh,ba),"blend_50":(.5*bh+.5*oh,.5*ba+.5*oa)}

def seal(doc,*,now=None):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError("NAIVE_NOW")
    now=now.astimezone(timezone.utc)
    fields(doc,"protocol league fixture history")
    if doc["protocol"]!=PROTOCOL or doc["league"] not in LEAGUES:raise ValueError("PROTOCOL_SCOPE")
    f=doc["fixture"];fields(f,"home away kickoff_utc sources")
    h,a=identifier(f["home"]),identifier(f["away"])
    if h==a:raise ValueError("SAME_TEAM")
    ko=instant(f["kickoff_utc"])
    if not START<=now<ko<END or not timedelta(minutes=10)<=ko-now<=timedelta(hours=24):
        raise ValueError("PREMATCH_WINDOW")
    sources=f["sources"]
    if type(sources) is not list or len(sources)!=2:raise ValueError("TWO_SOURCE_REQUIRED")
    providers=set()
    for s in sources:
        fields(s,"provider fixture_id home away kickoff_utc observed_utc status")
        provider=identifier(s["provider"]).casefold();identifier(s["fixture_id"])
        if provider in providers:raise ValueError("DUPLICATE_PROVIDER_LABEL")
        providers.add(provider)
        if (s["home"],s["away"],instant(s["kickoff_utc"]),s["status"])!=(h,a,ko,"SCHEDULED"):
            raise ValueError("FIXTURE_DISAGREEMENT")
        if not timedelta(0)<=now-instant(s["observed_utc"])<=timedelta(hours=6):raise ValueError("STALE_FIXTURE")
    history=doc["history"]
    if type(history) is not list or not 50<=len(history)<=MAX_HISTORY:raise ValueError("HISTORY_SCOPE")
    rows=[];seen=set()
    for r in history:
        fields(r,"league match_id home away kickoff_utc observed_utc score status")
        if r["league"]!=doc["league"] or r["status"]!="FINAL_REGULATION":raise ValueError("HISTORY_SCOPE")
        key=identifier(r["match_id"])
        if key in seen:raise ValueError("DUPLICATE_HISTORY_ID")
        seen.add(key)
        day=instant(r["kickoff_utc"]);obs=instant(r["observed_utc"])
        if not (HISTORY_START<=day.date()<ko.date() and day+timedelta(minutes=120)<=obs<=now):
            raise ValueError("HISTORY_TIME_LEAKAGE")
        rh,ra=identifier(r["home"]),identifier(r["away"])
        if rh==ra or type(r["score"]) is not list or len(r["score"])!=2 or any(type(v) is not int or not 0<=v<=30 for v in r["score"]):
            raise ValueError("HISTORY_SCORE")
        rows.append((day.date().isoformat(),rh,ra,*r["score"]))
    if len({r[:3] for r in rows})!=len(rows):raise ValueError("DUPLICATE_HISTORY_FIXTURE")
    rates=prior_rates(rows,h,a)
    models={}
    for name,(hr,ar) in rates.items():
        grid=score_matrix(hr,ar);p=one_x_two(grid)
        models[name]={"goal_rates":[hr,ar],"probabilities_1x2":[p[k] for k in OUTCOMES],
                      "score_matrix_sha256":digest(grid)}
    out={"protocol":PROTOCOL,"captured_utc":now.isoformat(),"league":doc["league"],
         "fixture_key":digest([doc["league"],h,a,ko.isoformat()]),"fixture":f,
         "input_sha256":digest(doc),"history_rows":len(rows),"models":models,
         "same_day_results_excluded":True,"source_labels_distinct_not_authenticated":True,
         "external_timestamp_attested":False,"history_truth_verified":False,
         "actual_market_quotes_verified":False,"authenticated_forward_samples":0,
         "positive_ev_verified":False,"production_recommendations":"DISABLED","status":"HOLD"}
    return {"record":out,"record_sha256":digest(out)}

def load(path):
    with Path(path).open("rb") as f:raw=f.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise ValueError("INPUT_SIZE")
    return json.loads(raw.decode("utf-8"),object_pairs_hook=unique_object,parse_constant=reject_constant)
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",required=True);p.add_argument("--output",required=True)
    a=p.parse_args()
    result=seal(load(a.input))
    with Path(a.output).open("x",encoding="utf-8") as f:json.dump(result,f,sort_keys=True,allow_nan=False)
if __name__=="__main__":main()
