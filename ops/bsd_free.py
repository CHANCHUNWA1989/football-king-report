"""BSD free football API backup: research only, no raw odds or credentials.

License https://sports.bzzoiro.com/docs/api-license/
Free API is consensus 1X2 rather than executable per-bookmaker odds.
This source stays separated from The Odds API and main recommendations
until point-in-time production parity has been validated.
"""
import argparse, json, math, os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from team_identity import team_id

BASE="https://sports.bzzoiro.com"
SCHEMA="football-king-bsd-free-research-v1"
LICENSE=BASE+"/docs/api-license/"
MAX_CALLS=3
MAX_BYTES=1_800_000
MAX_MARKETS=70

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("UNTRUSTED_BSD_REDIRECT")

def stamp(value):
    if not isinstance(value,str): raise ValueError("INVALID_BSD_TIME")
    x=datetime.fromisoformat(value.replace("Z","+00:00"))
    if x.tzinfo is None: raise ValueError("NAIVE_BSD_TIMESTAMP")
    return x.astimezone(timezone.utc)

def read(path,token,client=None):
    if not token or not path.startswith("/api/v2/") or "token=" in path:
        raise ValueError("DISALLOWED_BSD_REQUEST")
    req=Request(BASE+path,headers={
        "Authorization":"Token "+token,
        "Accept":"application/json",
        "User-Agent":"FootballKingResearchBSD/1.0"})
    opener=client or build_opener(NoRedirect()).open
    try:
        with opener(req,timeout=14) as response:
            payload=response.read(MAX_BYTES+1)
        if len(payload)>MAX_BYTES:raise ValueError("BSD_TOO_LARGE")
        return json.loads(payload.decode("utf-8"))
    except HTTPError as e:
        if e.code in (401,403):raise ValueError("BSD_ACCESS_REJECTED") from None
        if e.code==402:raise ValueError("BSD_PAID_ENDPOINT") from None
        if e.code==429:raise ValueError("BSD_QUOTA_EXHAUSTED") from None
        raise ValueError("BSD_HTTP_ERROR") from None
    except (URLError,OSError,TimeoutError):
        raise ValueError("BSD_NETWORK_ERROR") from None

def records(x):
    if isinstance(x,list):return x
    if isinstance(x,dict) and isinstance(x.get("results"),list):return x["results"]
    raise ValueError("BSD_UNKNOWN_PAGED_SCHEMA")

def name(x):
    if isinstance(x,str):return x.strip()[:120]
    if isinstance(x,dict):return name(x.get("name"))
    return ""

def league_code(text,country):
    n=" ".join(name(text).lower().replace("-"," ").split())
    c=name(country).lower()
    pairs={
        ("premier league","england"):"epl",
        ("championship","england"):"championship",
        ("efl championship","england"):"championship",
        ("bundesliga","germany"):"bundesliga",
        ("1. bundesliga","germany"):"bundesliga",
        ("la liga","spain"):"laliga",
        ("primera división","spain"):"laliga",
        ("serie a","italy"):"seriea",
        ("ligue 1","france"):"ligue1"}
    return pairs.get((n,c))

def parse_catalog(doc):
    out={}
    for row in records(doc)[:200]:
        if not isinstance(row,dict) or type(row.get("id")) is not int:continue
        code=league_code(row.get("name"),row.get("country"))
        if code:out[row["id"]]=code
    return out

def parse_fixtures(doc,catalog,now):
    out={}
    for row in records(doc)[:200]:
        if not isinstance(row,dict) or type(row.get("id")) is not int:continue
        rawid=row.get("league_id")
        if rawid is None and isinstance(row.get("league"),dict):
            rawid=row["league"].get("id")
        if rawid not in catalog:continue
        home,away=name(row.get("home_team")),name(row.get("away_team"))
        if not home or not away or home==away:continue
        league=catalog[rawid]
        if not team_id(league,home) or not team_id(league,away):continue
        try:ko=stamp(row.get("start_time") or row.get("kickoff") or row.get("start_at"))
        except (ValueError,TypeError,OverflowError):continue
        if not now+timedelta(minutes=10)<ko<=now+timedelta(days=8):continue
        if str(row.get("status") or "upcoming").lower() not in ("upcoming","scheduled"):
            continue
        out[row["id"]]={"league":league,"home":home,"away":away,"kickoff_utc":ko.isoformat()}
    return out

def derive(doc,fixtures,now):
    groups={}
    for row in records(doc)[:200]:
        if not isinstance(row,dict) or row.get("market") not in ("1x2","1X2"):continue
        ident=row.get("event_id")
        if type(ident) is not int or ident not in fixtures:continue
        if row.get("bookmaker_slug")!="consensus":continue
        k=row.get("outcome")
        price=row.get("decimal_odds")
        if k not in ("HOME","DRAW","AWAY") or type(price) not in (int,float):continue
        if not math.isfinite(price) or not 1.01<=price<=500:continue
        try:updated=stamp(row["updated_at"])
        except (KeyError,ValueError,TypeError,OverflowError):continue
        if not -timedelta(minutes=5)<=now-updated<=timedelta(hours=12):continue
        vals=groups.setdefault(ident,{})
        vals[k]=(price,updated) if k not in vals else None
    out=[]
    for event_id,values in groups.items():
        if set(values)!={"HOME","DRAW","AWAY"} or any(x is None for x in values.values()):
            continue
        odds=[1/values[k][0] for k in ("HOME","DRAW","AWAY")]
        overround=sum(odds)
        if not .98<=overround<=1.35:continue
        match=fixtures[event_id]
        last=max(values[k][1] for k in ("HOME","DRAW","AWAY"))
        if last>=stamp(match["kickoff_utc"]):continue
        p=[round(v/overround,7) for v in odds]
        out.append({**match,"source_event_id":str(event_id),
                    "market_last_update_utc":last.isoformat(),
                    "p_home":p[0],"p_draw":p[1],"p_away":p[2],
                    "market_source":"BSD_FREE_CONSENSUS_ONLY",
                    "raw_prices_published":False,
                    "not_executable_odds":True})
        if len(out)==MAX_MARKETS:break
    return out

def collect(*,now=None,token=None,client=None):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError("NAIVE_NOW")
    token=token if token is not None else os.environ.get("BSD_FREE_API_TOKEN","")
    out={"schema":SCHEMA,"provider":"bzzoiro_sports_data",
         "captured_utc":now.isoformat(),"status":"NOT_CONFIGURED",
         "key_present":bool(token),"requests_attempted":0,"max_calls":MAX_CALLS,
         "free_plan_max_daily_calls_documented":7500,
         "league_count":0,"fixture_count":0,"market_count":0,
         "events":[],"warnings":[],"license_url":LICENSE,
         "free_tier_only":True,"raw_quotes_published":False,
         "licensed_per_bookmaker_prices_available":False,
         "independently_verified_market_advantage":False,
         "replaces_current_market_automatically":False,
         "production_recommendations":"DISABLED"}
    if not token:
        out["warnings"]=["SET_BSD_FREE_API_TOKEN_IN_REPO_SECRETS"]
        return out
    params=urlencode({"date_from":now.date().isoformat(),
        "date_to":(now+timedelta(days=8)).date().isoformat(),
        "status":"upcoming","limit":200})
    paths=["/api/v2/leagues/?limit=200","/api/v2/events/?"+params,
           "/api/v2/odds/?market=1x2&limit=200"]
    docs=[]
    for path in paths:
        out["requests_attempted"]+=1
        if out["requests_attempted"]>MAX_CALLS:raise ValueError("BUDGET_EXCEEDED")
        try:docs.append(read(path,token,client))
        except (ValueError,TypeError) as e:
            allowed={"BSD_ACCESS_REJECTED","BSD_PAID_ENDPOINT","BSD_QUOTA_EXHAUSTED",
                     "BSD_HTTP_ERROR","BSD_NETWORK_ERROR","BSD_TOO_LARGE"}
            out["warnings"]=[str(e) if str(e) in allowed else "UNKNOWN_VENDOR_ERROR"]
            out["status"]="HOLD"
            return out
    try:
        leagues=parse_catalog(docs[0])
        matches=parse_fixtures(docs[1],leagues,now)
        odds=derive(docs[2],matches,now)
    except (ValueError,TypeError,KeyError,OverflowError):
        out["status"]="HOLD"
        out["warnings"]=["BSD_UNVERIFIED_FIELD_FORMAT"]
        return out
    out.update(status="RESEARCH_ONLY" if odds else "NO_COMPARABLE_MARKET",
        league_count=len(set(leagues.values())),fixture_count=len(matches),
        market_count=len(odds),events=odds,
        warnings=["CONSENSUS_IS_NOT_AN_EXECUTABLE_BETTING_QUOTE"])
    return out

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",default="sources/bsd_latest.json")
    args=parser.parse_args()
    out=collect()
    p=Path(args.output)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:out[k] for k in (
        "status","key_present","requests_attempted","league_count",
        "fixture_count","market_count","warnings","production_recommendations")},
        ensure_ascii=False))

if __name__=="__main__":main()
