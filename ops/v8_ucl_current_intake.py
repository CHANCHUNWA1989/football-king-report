"""V8.5 bounded current UCL season intake diagnostics; no qualified forecasts."""
import argparse
from collections import Counter
from datetime import datetime,timezone,timedelta,date
import json
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
from ops.v5_ucl_source_gate import FD,TS,fetch,ident,utc,parse_ts
from ops.free_api_rate_limit import reserve

TS_SEASON="https://www.thesportsdb.com/api/v1/json/123/eventsseason.php"
HK=ZoneInfo("Asia/Hong_Kong")
def season_at(now):
    d=now.astimezone(HK).date()
    return d.year if d.month>=7 else d.year-1
def receipt(entry,now):
    if not 0<=(now-utc(entry["captured_utc"])).total_seconds()<=900:raise ValueError("STALE_CAPTURE")
    digest=entry["sha256"]
    if not isinstance(digest,str) or len(digest)!=64 or any(c not in "0123456789abcdef" for c in digest):raise ValueError("BAD_DIGEST")
    return {"captured_utc":entry["captured_utc"],"payload_sha256":digest}
def score_pair(s):
    if not isinstance(s,dict):raise ValueError("BAD_SCORE")
    x,y=s.get("home"),s.get("away")
    if any(type(v) is not int or not 0<=v<=20 for v in (x,y)):raise ValueError("BAD_SCORE")
    return x,y
def fd_diagnostics(entry,now,year):
    meta=receipt(entry,now);doc=entry["payload"]
    if doc.get("competition",{}).get("code")!="CL":raise ValueError("WRONG_COMPETITION")
    rows=doc.get("matches")
    if not isinstance(rows,list) or len(rows)>350:raise ValueError("BAD_MATCH_LIST")
    seen=set();pairs=set();rounds=Counter();teams=set();per_round=Counter();finished=0;future=0;other=0
    for r in rows:
        if r.get("competition",{}).get("code")!="CL":raise ValueError("WRONG_ROW_COMPETITION")
        season=r.get("season",{});start=date.fromisoformat(season["startDate"])
        if start.year!=year:raise ValueError("WRONG_SEASON")
        mid=ident(r["id"])
        if mid in seen:raise ValueError("DUPLICATE_EVENT")
        seen.add(mid)
        if r.get("stage") not in ("LEAGUE_STAGE","REGULAR_SEASON","GROUP_STAGE"):continue
        rd=r.get("matchday")
        if type(rd) is not int or not 1<=rd<=8:raise ValueError("BAD_MATCHDAY")
        h,a=ident(r["homeTeam"]["id"]),ident(r["awayTeam"]["id"])
        if h==a or frozenset((h,a)) in pairs:raise ValueError("DUPLICATE_PAIR")
        pairs.add(frozenset((h,a)));teams.update((h,a));rounds[rd]+=1
        for t in (h,a):
            per_round[rd,t]+=1
            if per_round[rd,t]>1:raise ValueError("REPEATED_TEAM_IN_ROUND")
        ko=utc(r["utcDate"])
        if not datetime(year,7,1,tzinfo=timezone.utc)<=ko<datetime(year+1,7,1,tzinfo=timezone.utc):raise ValueError("DATE_OUTSIDE_SEASON")
        status=r.get("status");s=r.get("score",{})
        if status=="FINISHED":
            if ko+timedelta(hours=2)>now or s.get("duration")!="REGULAR":raise ValueError("UNSAFE_FINAL")
            score_pair(s.get("fullTime"))
            if ko.astimezone(HK).date()<now.astimezone(HK).date():finished+=1
            else:other+=1
        elif status in ("SCHEDULED","TIMED"):
            if s.get("winner") is not None or any(v is not None for v in s.get("fullTime",{}).values()):raise ValueError("RESULT_BEARING_FIXTURE")
            if now+timedelta(minutes=10)<ko<=now+timedelta(days=2):future+=1
        else:other+=1
    complete=len(teams)==36 and rounds==Counter({i:18 for i in range(1,9)})
    return {**meta,"status":"OBSERVED_SINGLE_SOURCE" if complete else "PARTIAL",
        "returned_rows":len(rows),"phase_rows":sum(rounds.values()),"complete_phase_schedule":complete,
        "prior_hk_day_finished":finished,"future_within_48h":future,"other_or_same_day":other}
def ts_diagnostics(entry,now,year):
    meta=receipt(entry,now);rows=entry["payload"].get("events")
    if rows is None:rows=[]
    if not isinstance(rows,list) or len(rows)>250:raise ValueError("BAD_MATCH_LIST")
    ids=set()
    for r in rows:
        if str(r.get("idLeague"))!="4480" or r.get("strSport")!="Soccer" or r.get("strSeason")!=f"{year}-{year+1}":raise ValueError("WRONG_SCOPE")
        mid=ident(r["idEvent"])
        if mid in ids:raise ValueError("DUPLICATE_EVENT")
        ids.add(mid)
    # This free endpoint has a documented row cap. Never infer full phase or training readiness.
    return {**meta,"status":"PARTIAL" if rows else "EMPTY","returned_rows":len(rows),
        "complete_phase_schedule":False,"prior_hk_day_finished":None,"free_endpoint_row_limit":15}
def build(fd,ts,day,now):
    year=season_at(now)
    out={"schema":"v8-5-ucl-current-source-intake-v1","as_of_utc":now.isoformat(),"season":year,
        "providers":{},"current_training_ready":False,"current_fixture_forecasts":0,
        "verified_forward_sample_credit":0,"independent_source_agreement":False,
        "production_recommendations":"DISABLED","status":"HOLD"}
    for label,entry,parser in (("football_data_org",fd,fd_diagnostics),("thesportsdb_season",ts,ts_diagnostics)):
        if entry is None:out["providers"][label]={"status":"NOT_CONFIGURED_OR_UNAVAILABLE"};continue
        try:out["providers"][label]=parser(entry,now,year)
        except (ValueError,TypeError,KeyError,AttributeError):out["providers"][label]={"status":"HOLD_INVALID_OR_STALE"}
    if day is not None:
        try:
            meta=receipt(day,now)
            rows=parse_ts(day["payload"])
            out["providers"]["thesportsdb_day"]={**meta,"status":"RESEARCH_ONLY","future_within_48h":sum(now+timedelta(minutes=10)<r[3]<=now+timedelta(days=2) for r in rows)}
        except (ValueError,TypeError,KeyError,AttributeError):out["providers"]["thesportsdb_day"]={"status":"HOLD_INVALID_OR_STALE"}
    else:out["providers"]["thesportsdb_day"]={"status":"UNAVAILABLE"}
    return out
def main():
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);p.add_argument("--ledger",required=True)
    p.add_argument("--probe-sportsdb",action="store_true");a=p.parse_args()
    now=datetime.now(timezone.utc);year=season_at(now);ts=day=None
    # Two bounded free public requests; no retries, no secret reading.
    if a.probe_sportsdb:
        try:
            reserve(a.ledger)
            ts=fetch(TS_SEASON+"?"+urlencode({"id":"4480","s":f"{year}-{year+1}"}),{})
        except (OSError,ValueError,TypeError):pass
        try:
            reserve(a.ledger)
            day=fetch(TS+"?"+urlencode({"d":now.date().isoformat(),"s":"Soccer","l":"4480"}),{})
        except (OSError,ValueError,TypeError):pass
    end=datetime.now(timezone.utc)
    if season_at(end)!=year:raise ValueError("SEASON_CHANGED")
    # FD diagnostics accepts an authorized captured response through the Python API only.
    # Existing optional FD connector requires owner-provisioned credentials; do not access them here.
    out=build(None,ts,day,end)
    out["football_data_access"]="OWNER_PROVISIONED_TOKEN_REQUIRED_FOR_MATCH_ENDPOINT"
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
