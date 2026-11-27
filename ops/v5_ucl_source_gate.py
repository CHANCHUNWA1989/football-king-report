"""UCL schedule source intake, research only. No odds, training or promotion.

Football-data.org and TheSportsDB official API endpoints only.
Provider team names are never used to establish cross-source identity.
Crosswalk entries are explicit native-ID pairs; local metadata is not attestation.
Only aggregate diagnostics are published; raw responses and credentials are not.
"""
import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

from ops.free_api_rate_limit import reserve

FD="https://api.football-data.org/v4/competitions/CL/matches"
TS="https://www.thesportsdb.com/api/v1/json/123/eventsday.php"
MAX_BYTES=2_000_000
MAX_ROWS=250
MAX_AGE=900

def utc(x):
    if not isinstance(x,str):raise ValueError("MISSING_CLOCK")
    d=datetime.fromisoformat(x.replace("Z","+00:00"))
    if d.tzinfo is None or d.utcoffset() is None:raise ValueError("NAIVE_CLOCK")
    return d.astimezone(timezone.utc)

def ident(x):
    if type(x) is int:x=str(x)
    if not isinstance(x,str) or not x.isascii() or not x.isdecimal() or not 1<=len(x)<=18 or int(x)<=0:
        raise ValueError("INVALID_NATIVE_ID")
    return str(int(x))

def parse_fd(doc):
    if not isinstance(doc,dict) or doc.get("competition",{}).get("code")!="CL":
        raise ValueError("WRONG_COMPETITION")
    rows=doc.get("matches")
    if not isinstance(rows,list) or len(rows)>MAX_ROWS:raise ValueError("INVALID_MATCH_LIST")
    out=[]
    for r in rows:
        if not isinstance(r,dict):raise ValueError("INVALID_ROW")
        if r.get("status") not in ("SCHEDULED","TIMED"):continue
        if r.get("competition",{}).get("code")!="CL":raise ValueError("WRONG_ROW_COMPETITION")
        score=r.get("score",{})
        if score.get("winner") is not None or any(v is not None for v in score.get("fullTime",{}).values()):
            raise ValueError("RESULT_BEARING_SCHEDULE")
        out.append((ident(r["id"]),ident(r["homeTeam"]["id"]),ident(r["awayTeam"]["id"]),utc(r["utcDate"])))
    return unique(out)

def parse_ts(doc):
    if not isinstance(doc,dict):raise ValueError("INVALID_RESPONSE")
    rows=doc.get("events")
    if rows is None:return []
    if not isinstance(rows,list) or len(rows)>MAX_ROWS:raise ValueError("INVALID_MATCH_LIST")
    out=[]
    for r in rows:
        if not isinstance(r,dict):raise ValueError("INVALID_ROW")
        if str(r.get("idLeague"))!="4480" or r.get("strSport")!="Soccer":continue
        if r.get("intHomeScore") is not None or r.get("intAwayScore") is not None:continue
        if str(r.get("strStatus","")).strip().lower() not in ("","not started","ns","scheduled","match scheduled","time to be defined"):
            continue
        stamp=r.get("strTimestamp")
        if not isinstance(stamp,str) or "T" not in stamp:continue
        # TheSportsDB documents timestamps as UTC; never infer from local time fields.
        d=datetime.fromisoformat(stamp.replace("Z","+00:00"))
        if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
        out.append((ident(r["idEvent"]),ident(r["idHomeTeam"]),ident(r["idAwayTeam"]),d.astimezone(timezone.utc)))
    return unique(out)

def unique(rows):
    ids=set()
    for event,h,a,_ in rows:
        if event in ids or h==a:raise ValueError("DUPLICATE_OR_INVALID_FIXTURE")
        ids.add(event)
    return rows

def crosswalk(doc):
    if not isinstance(doc,dict) or doc.get("schema")!="v5-ucl-native-id-crosswalk-v1" or not isinstance(doc.get("pairs"),list) or len(doc["pairs"])>500:
        raise ValueError("INVALID_CROSSWALK")
    out={};used=set()
    for r in doc["pairs"]:
        h,a=ident(r["football_data_team_id"]),ident(r["sportsdb_team_id"])
        if h in out or a in used or not isinstance(r.get("evidence_reference"),str) or not r["evidence_reference"].startswith("https://"):
            raise ValueError("AMBIGUOUS_OR_UNSUPPORTED_CROSSWALK")
        out[h]=a;used.add(a)
    return out

def gate(fd,ts,mapping,now):
    now=utc(now.isoformat())
    report={"schema":"football-king-v5-ucl-source-gate-v1","status":"HOLD","as_of_utc":now.isoformat(),
            "providers":{},"candidate_schedule_agreements":0,"eligible_model_inputs":0,
            "source_identity_independently_authenticated":False,"crosswalk_independently_verified":False,
            "publisher_independence_verified":False,"historical_training_ready":False,
            "production_recommendations":"DISABLED","predictions_count":0}
    def rows(label,entry,parser):
        if entry is None:
            report["providers"][label]={"status":"NOT_CONFIGURED_OR_UNAVAILABLE","future_fixtures":0};return []
        try:
            captured=utc(entry["captured_utc"])
            if not 0<=(now-captured).total_seconds()<=MAX_AGE:raise ValueError("STALE_OR_FUTURE_CAPTURE")
            parsed=parser(entry["payload"])
            future=[r for r in parsed if now+timedelta(minutes=10)<r[3]<=now+timedelta(days=2)]
            report["providers"][label]={"status":"RESEARCH_OBSERVED","future_fixtures":len(future),
                "captured_utc":captured.isoformat(),"payload_sha256":entry.get("sha256")}
            return future
        except (ValueError,TypeError,KeyError,AttributeError,OverflowError):
            report["providers"][label]={"status":"HOLD_INVALID_OR_STALE","future_fixtures":0};return []
    f=rows("football_data_org",fd,parse_fd);s=rows("thesportsdb",ts,parse_ts)
    try:m=crosswalk(mapping)
    except (ValueError,TypeError,KeyError,AttributeError):
        report["reason"]="NATIVE_ID_CROSSWALK_REQUIRED";return report
    if not f or not s:
        report["reason"]="TWO_FRESH_PROVIDER_RESPONSES_REQUIRED";return report
    left=defaultdict(list);right=defaultdict(list)
    for event,h,a,t in f:
        if h in m and a in m:left[(m[h],m[a])].append((event,t))
    for event,h,a,t in s:right[(h,a)].append((event,t))
    rejected=Counter()
    for pair,items in left.items():
        other=right.get(pair,[])
        if len(items)!=1 or len(other)!=1:rejected["missing_or_ambiguous_pair"]+=1;continue
        if items[0][1]!=other[0][1]:rejected["kickoff_disagreement"]+=1;continue
        report["candidate_schedule_agreements"]+=1
    report["rejections"]=dict(rejected)
    report["reason"]="INDEPENDENT_CROSSWALK_AND_HISTORICAL_MODEL_EVIDENCE_REQUIRED"
    return report

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError("UNEXPECTED_REDIRECT")

def fetch(url,headers):
    req=Request(url,headers={"Accept":"application/json","User-Agent":"FootballKingResearch/5.0",**headers})
    with build_opener(NoRedirect()).open(req,timeout=12) as response:
        raw=response.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise ValueError("RESPONSE_LIMIT")
    return {"captured_utc":datetime.now(timezone.utc).isoformat(),
            "sha256":hashlib.sha256(raw).hexdigest(),"payload":json.loads(raw.decode("utf-8"))}

def main():
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);p.add_argument("--crosswalk")
    p.add_argument("--probe-sportsdb",action="store_true");p.add_argument("--probe-football-data",action="store_true")
    p.add_argument("--ledger");a=p.parse_args()
    day=datetime.now(timezone.utc).date();fd=ts=None;fail={}
    if a.probe_football_data:
        token=os.environ.get("FOOTBALL_DATA_ORG_TOKEN")
        if token:
            try:fd=fetch(FD+"?"+urlencode({"dateFrom":day.isoformat(),"dateTo":(day+timedelta(days=1)).isoformat()}),{"X-Auth-Token":token})
            except (OSError,ValueError,TypeError):fail["football_data_org"]="REQUEST_UNAVAILABLE"
        else:fail["football_data_org"]="NOT_CONFIGURED"
    if a.probe_sportsdb:
        if not a.ledger:raise ValueError("RATE_LEDGER_REQUIRED")
        try:
            reserve(a.ledger)
            ts=fetch(TS+"?"+urlencode({"d":day.isoformat(),"s":"Soccer","l":"4480"}),{})
        except (OSError,ValueError,TypeError):fail["thesportsdb"]="REQUEST_UNAVAILABLE"
    mapping={"schema":"v5-ucl-native-id-crosswalk-v1","pairs":[]}
    if a.crosswalk:
        path=Path(a.crosswalk)
        if path.stat().st_size>100000:raise ValueError("CROSSWALK_LIMIT")
        mapping=json.loads(path.read_text(encoding="utf-8"))
    report=gate(fd,ts,mapping,datetime.now(timezone.utc));report["probe_diagnostics"]=fail
    report["utc_query_day"]=day.isoformat()
    Path(a.output).write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(report,allow_nan=False))
if __name__=="__main__":main()
