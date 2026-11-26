"""Optional six-league Football-Data.org schedule adapter; no price or result admission."""
import os
import time
from collections import Counter,defaultdict
from datetime import timedelta
from urllib.parse import urlencode
from secondary_sources import FD_CODE,fetch
from live_core_same_batch_collection import clock,stamp,MAX_BATCH_AGE,validate_projection
from team_identity import team_id

STOP={"RATE_LIMITED","KEY_REJECTED","PLAN_OR_LEAGUE_RESTRICTED"}
def project(league,body,received):
    if received.tzinfo is None:raise ValueError("NAIVE_CLOCK")
    if not isinstance(body,dict) or not isinstance(body.get("matches"),list) or len(body["matches"])>160:
        raise ValueError("SOURCE_SCOPE")
    rows=body["matches"];reasons=Counter();candidates=[]
    all_ids=Counter(r.get("id") for r in rows if isinstance(r,dict) and type(r.get("id")) is int)
    for r in rows:
        if not isinstance(r,dict):reasons["ROW_SHAPE"]+=1;continue
        comp=r.get("competition")
        if not isinstance(comp,dict) or comp.get("code")!=FD_CODE[league]:reasons["COMPETITION_MISMATCH"]+=1;continue
        # TIMED means a kickoff time is set; date-only SCHEDULED is withheld.
        if r.get("status")!="TIMED":reasons["STATUS_NOT_TIMED"]+=1;continue
        score=r.get("score")
        if not isinstance(score,dict) or not isinstance(score.get("fullTime"),dict) or any(k not in score["fullTime"] or score["fullTime"][k] is not None for k in ("home","away")):
            reasons["SCORE_PRESENT_OR_UNKNOWN"]+=1;continue
        try:ko=stamp(r["utcDate"])
        except (KeyError,TypeError,ValueError,OverflowError):reasons["INVALID_UTC"]+=1;continue
        if not received<ko<=received+timedelta(days=8):reasons["OUTSIDE_WINDOW"]+=1;continue
        h,a=r.get("homeTeam"),r.get("awayTeam")
        if not isinstance(h,dict) or not isinstance(a,dict):reasons["TEAM_INVALID"]+=1;continue
        h,a=team_id(league,h.get("name")),team_id(league,a.get("name"))
        if not h or not a or h==a:reasons["TEAM_INVALID"]+=1;continue
        ident=r.get("id")
        if type(ident) is not int or ident<=0:reasons["ID_INVALID"]+=1;continue
        if all_ids[ident]!=1:reasons["DUPLICATE_ID"]+=1;continue
        candidates.append({"league":league,"home_id":h,"away_id":a,"native_id":str(ident),"kickoff_utc":ko.isoformat(),"received_utc":received.isoformat()})
    keys=Counter((r["home_id"],r["away_id"],r["kickoff_utc"]) for r in candidates)
    pairs=Counter((r["home_id"],r["away_id"]) for r in candidates)
    out=[]
    for r in candidates:
        if keys[(r["home_id"],r["away_id"],r["kickoff_utc"])]!=1:reasons["DUPLICATE_FIXTURE"]+=1;continue
        if pairs[(r["home_id"],r["away_id"])]!=1:reasons["AMBIGUOUS_PAIR_KICKOFF"]+=1;continue
        reasons["ACCEPTED_LOCAL"]+=1;out.append(r)
    if sum(reasons.values())!=len(rows):raise ValueError("DENOMINATOR")
    return out,dict(reasons)

def collect(leagues,*,token=None,fetcher=fetch,now=clock,pause=time.sleep):
    if not isinstance(leagues,list) or len(leagues)!=len(set(leagues)) or not set(leagues)<=set(FD_CODE):raise ValueError("LEAGUE_SCOPE")
    token=os.environ.get("FOOTBALL_DATA_ORG_TOKEN","") if token is None else token
    out=[];attempts={};stop=False
    for k in leagues:
        if not token or stop:break
        if attempts:pause(7)
        t=now();query=urlencode({"dateFrom":t.date().isoformat(),"dateTo":(t+timedelta(days=8)).date().isoformat()})
        body,status=fetcher("football_data_org",f"https://api.football-data.org/v4/competitions/{FD_CODE[k]}/matches?"+query,{"X-Auth-Token":token})
        received=now();rows=[];reasons={}
        if status=="OK":
            try:rows,reasons=project(k,body,received)
            except (TypeError,ValueError,OverflowError):status="INVALID_DATA"
        if status not in ("OK","RATE_LIMITED","KEY_REJECTED","PLAN_OR_LEAGUE_RESTRICTED","HTTP_ERROR","NETWORK_ERROR","INVALID_DATA"):status="OTHER_ERROR"
        attempts[k]={"status":status,"rows":len(rows),"disposition":reasons}
        out.extend(rows);stop=status in STOP
    return out,{"configured":bool(token),"requests_attempted":len(attempts),"request_budget":6,"attempts":attempts,
                "unrequested_leagues":[k for k in leagues if k not in attempts],"provider_stop":stop,
                "authenticated_forward_samples":0,"production_recommendations":"DISABLED"}

def review(markets,rows,*,finished):
    validate_projection(markets,960,market=True);validate_projection(rows,960)
    if finished.tzinfo is None:raise ValueError("NAIVE_CLOCK")
    def key(r):return (r["league"],r["home_id"],r["away_id"])
    ids=Counter(r["native_id"] for r in rows);mi=Counter(r["native_id"] for r in markets)
    mk=Counter((key(r),stamp(r["kickoff_utc"])) for r in markets)
    mp=Counter(key(r) for r in markets)
    idx=defaultdict(list)
    for r in rows:idx[key(r)].append(r)
    out={k:Counter() for k in FD_CODE}
    for r in markets:
        c=out[r["league"]];ko,at,up=(stamp(r[k]) for k in ("kickoff_utc","received_utc","oldest_market_update_utc"))
        if not timedelta(0)<=finished-at<=MAX_BATCH_AGE or not timedelta(0)<=at-up<=MAX_BATCH_AGE or not timedelta(0)<=finished-up<=MAX_BATCH_AGE or finished>=ko-timedelta(minutes=10):
            c["MARKET_TIME_REJECTED"]+=1;continue
        if mi[r["native_id"]]!=1 or mk[(key(r),ko)]!=1 or mp[key(r)]!=1:c["MARKET_AMBIGUOUS"]+=1;continue
        x=idx[key(r)]
        if not x:c["NO_MATCH"]+=1;continue
        if len(x)!=1 or ids[x[0]["native_id"]]!=1:c["SOURCE_AMBIGUOUS"]+=1;continue
        if not timedelta(0)<=finished-stamp(x[0]["received_utc"])<=MAX_BATCH_AGE:c["SOURCE_STALE"]+=1;continue
        c["EXACT_LOCAL_AGREEMENT" if stamp(x[0]["kickoff_utc"])==ko else "KICKOFF_CONFLICT"]+=1
    if sum(sum(v.values()) for v in out.values())!=len(markets):raise ValueError("REVIEW_DENOMINATOR")
    return {"by_league":{k:dict(v) for k,v in out.items()},"market_rows":len(markets),
            "local_agreements":sum(v["EXACT_LOCAL_AGREEMENT"] for v in out.values()),
            "independent_identity_authenticated":False,"authenticated_forward_samples":0,"production_recommendations":"DISABLED","status":"HOLD"}
