"""Explicit one-call API-Football live scope probe. Aggregate metadata only.
No automatic retries, no odds calls, no upstream time or independence claims.
"""
import argparse
import json
import os
from datetime import datetime, timezone
from secondary_sources import fetch

URL = "https://v3.football.api-sports.io/fixtures?live=all"
LIVE = {"1H","HT","2H","ET","BT","P","LIVE"}
MAX_ROWS = 1000

def summarize(body):
    if type(body) is not dict or body.get("errors"):
        raise ValueError("PROVIDER_REJECTED")
    rows=body.get("response")
    if type(rows) is not list or len(rows)>MAX_ROWS:
        raise ValueError("BAD_ROWS")
    counts={}
    for row in rows:
        if type(row) is not dict:
            continue
        f=row.get("fixture")
        if type(f) is not dict or type(f.get("id")) is not int or f["id"]<=0:
            continue
        ident=f["id"]
        if ident in counts:
            raise ValueError("DUPLICATE_PROVIDER_ID")
        s=f.get("status")
        g=row.get("goals")
        eligible=(type(s) is dict and s.get("short") in LIVE
                  and type(g) is dict and all(type(g.get(k)) is int and
                      0<=g[k]<=30 for k in ("home","away")))
        counts[ident]=eligible
    return len(rows),sum(counts.values())

def probe(*, key, allow=False, requester=None):
    out={"schema":"football-king-api-football-live-probe-v1",
         "checked_utc":datetime.now(timezone.utc).isoformat(),
         "status":"HOLD","reason":"EXPLICIT_ONE_CALL_REQUIRED",
         "requests_attempted":0,"returned_rows":0,"claimed_live_score_rows":0,
         "source_authenticated":False,"upstream_timestamp_verified":False,
         "red_cards_verified":False,"actual_xg_verified":False,
         "actual_live_odds_verified":False,"positive_ev_verified":False,
         "production_recommendations":"DISABLED"}
    if allow is not True:
        return out
    if type(key) is not str or not key.strip() or any(c in key for c in "\r\n"):
        out["reason"]="NOT_CONFIGURED"
        return out
    out["requests_attempted"]=1
    try:
        body,status=fetch("api_football",URL,{"x-apisports-key":key},requester=requester)
        if status!="OK":
            out["reason"]=status if status in {"KEY_REJECTED","PLAN_OR_LEAGUE_RESTRICTED",
                "RATE_LIMITED","HTTP_ERROR","NETWORK_ERROR","INVALID_DATA"} else "PROVIDER_FAILURE"
            return out
        out["returned_rows"],out["claimed_live_score_rows"]=summarize(body)
        out["reason"]="CLAIMED_LIVE_ROWS_ONLY" if out["claimed_live_score_rows"] else "NO_LIVE_ROWS"
    except (ValueError,TypeError,KeyError,OverflowError,AttributeError):
        out["reason"]="PROVIDER_REJECTED_OR_BAD_SCHEMA"
    return out

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--allow-one-call",action="store_true")
    a=p.parse_args(argv)
    print(json.dumps(probe(key=os.environ.get("API_FOOTBALL_KEY",""),allow=a.allow_one_call),sort_keys=True))

if __name__=="__main__":
    main()
