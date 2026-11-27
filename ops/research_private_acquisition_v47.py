"""Bounded private acquisition pilot for the existing PropLine free feed.

Run only in an authorized private runtime. No workflow, artifact, credential
logging, public dataset, or persistent raw response. CLI emits counts only.
"""
import argparse
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.request import Request,HTTPRedirectHandler,build_opener
from .research_private_propline_v43 import SPORTS,private_components
from .research_live_intake_v4 import decode,MAX_BYTES
from .research_candidate_gap_v6 import stamp
from .research_prospective_fusion_v38 import REGISTRATION_NOT_BEFORE
from .research_integrated_fusion_v45 import prepare
from .research_missing_fixture_discovery_v16 import candidates
from .research_calendar_gap_priority_v33 import selectors
from .research_archive_score_recovery_v14 import archive_snapshots
from .research_two_publisher_recovery_v15 import secondary_snapshots

ROOT="https://api.prop-line.com/v1"
FILTER="&bookmakers=pinnacle,bovada,fanduel,draftkings"
PATHS={l:f"/sports/{s}/odds?markets=h2h,spreads,totals{FILTER}" for l,s in SPORTS.items()}
RESERVE=75
MAX_CALLS=2
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError("redirect rejected")

def clock():
    return datetime.now(timezone.utc).isoformat()

def fetch(path,key):
    if path not in ("/sports",*PATHS.values()) or not isinstance(key,str) or not key:
        raise ValueError("invalid request")
    req=Request(ROOT+path,headers={"X-API-Key":key,"Accept":"application/json",
                                  "User-Agent":"FootballKingPrivateResearch/1.0"})
    try:
        with build_opener(NoRedirect()).open(req,timeout=15) as r:
            if r.status!=200 or r.geturl()!=req.full_url:raise ValueError("unexpected endpoint")
            body=r.read(MAX_BYTES-12)
            if len(body)>=MAX_BYTES-12:raise ValueError("response size")
            q=r.headers.get("X-Daily-Remaining")
        if not isinstance(q,str) or not q.isascii() or not q.isdecimal():
            raise ValueError("missing quota")
        return body,int(q)
    except (HTTPError,URLError,OSError,TimeoutError,ValueError,TypeError,OverflowError):
        raise ValueError("provider request rejected") from None

def envelope(body):
    if not isinstance(body,bytes):raise ValueError("response type")
    wrapped=b'{"events":'+body+b'}'
    d=decode(wrapped)
    if set(d)!={"events"} or not isinstance(d["events"],list):raise ValueError("response schema")
    return wrapped,d["events"]

def acquire(league,*,key,fetcher=fetch,now=clock):
    if league not in SPORTS:raise ValueError("unsupported league")
    report={"schema":"private-propline-acquisition-v47","status":"HOLD",
            "requests_attempted":0,"max_requests":MAX_CALLS,"remaining":None,
            "private_batches":0,"market_components":0,"production_recommendations":"DISABLED",
            "publication_allowed":False,"authenticated_samples":0}
    def stop(reason):
        report["reason"]=reason
        return [],report
    start=stamp(now())
    if start<stamp(REGISTRATION_NOT_BEFORE):return stop("BEFORE_REGISTRATION_WINDOW")
    if not isinstance(key,str) or not key:return stop("NOT_CONFIGURED")
    try:
        report["requests_attempted"]+=1
        cat,q=fetcher("/sports",key)
        if type(q) is not int or q<0:return stop("UNVERIFIED_QUOTA")
        report["remaining"]=q
        _,rows=envelope(cat)
        if q<=RESERVE:return stop("QUOTA_RESERVE")
        matches=[r for r in rows if isinstance(r,dict) and r.get("key")==SPORTS[league] and r.get("active") is True]
        if len(matches)!=1:return stop("LEAGUE_NOT_UNAMBIGUOUSLY_ACTIVE")
        report["requests_attempted"]+=1
        body,q=fetcher(PATHS[league],key)
        if type(q) is not int or q<0:
            report["remaining"]=None
            return stop("UNVERIFIED_QUOTA")
        report["remaining"]=q
        if q<RESERVE:return stop("QUOTA_RESERVE")
        end=stamp(now())
        if not timedelta(0)<=end-start<=timedelta(minutes=2):return stop("ACQUISITION_CLOCK_REJECTED")
        wrapped,_=envelope(body)
        batch={"raw":wrapped,"league":league,"captured_utc":end.isoformat()}
        components,_=private_components(wrapped,league=league,captured_utc=end.isoformat(),as_of=end.isoformat())
        report.update(private_batches=1,market_components=len(components),reason="PRIVATE_INPUT_VALIDATED")
        return [batch],report
    except (ValueError,KeyError,TypeError,OverflowError,AttributeError,RecursionError,OSError):
        return stop("PROVIDER_OR_INPUT_REJECTED")

def pilot(root,league,*,key,fetcher=fetch,now=clock):
    # Load bounded historical archives before spending quota.
    def read(path):
        if path.is_symlink() or not path.is_file():raise ValueError("unsafe archive")
        with path.open("rb") as f:b=f.read(MAX_BYTES+1)
        if not 0<len(b)<=MAX_BYTES:raise ValueError("archive size")
        return b
    raw=read(root/"evidence/settled.json");rows=candidates(raw)
    a,_=selectors(rows,primary=True);b,_=selectors(rows,primary=False)
    first=list(archive_snapshots(root/"sources/live_germany/history",a))
    second=list(secondary_snapshots(root/"sources/history",b))
    batches,acquisition=acquire(league,key=key,fetcher=fetcher,now=now)
    if not batches:return {"acquisition":acquisition,"local_receipts":0,"status":"HOLD",
                           "production_recommendations":"DISABLED","external_witnesses_created":0}
    packets,report=prepare(raw,first,second,None,batches,as_of=now(),include_supplemental=True)
    # Private packets are deliberately not returned by this count-only pilot.
    return {"acquisition":acquisition,"local_receipts":len(packets),
            "history_candidates":report["history_inventory"]["history_candidates"],
            "private_only":True,"external_witnesses_created":0,
            "authenticated_samples":0,"status":"HOLD","production_recommendations":"DISABLED"}

def main():
    p=argparse.ArgumentParser(description="Private, count-only research pilot")
    p.add_argument("--league",choices=tuple(SPORTS),required=True)
    p.add_argument("--authorized-private-runtime",action="store_true")
    args=p.parse_args()
    # Do not run a private licensed-data collector in public/shared CI.
    if not args.authorized_private_runtime or os.environ.get("GITHUB_ACTIONS")=="true":
        print('{"status":"HOLD","reason":"PRIVATE_RUNTIME_REQUIRED","production_recommendations":"DISABLED"}')
        return 2
    try:
        result=pilot(Path("."),args.league,key=os.environ.get("PROPLINE_API_KEY",""))
        print(json.dumps(result,sort_keys=True,allow_nan=False))
        return 0
    except (ValueError,KeyError,TypeError,OverflowError,AttributeError,RecursionError,OSError):
        print('{"status":"HOLD","reason":"PRIVATE_PILOT_REJECTED","production_recommendations":"DISABLED"}')
        return 1
if __name__=="__main__":
    raise SystemExit(main())
