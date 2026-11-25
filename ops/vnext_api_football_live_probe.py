"""Explicit one-call API-Football live scope probe. Aggregate metadata only.
No automatic retries, no odds calls, no upstream time or independence claims.
"""
import argparse
import json
import os
from datetime import datetime, timezone, timedelta
from secondary_sources import fetch

URL = "https://v3.football.api-sports.io/fixtures?live=all"
LIVE = {"1H","HT","2H","ET","BT","P","LIVE"}
MAX_ROWS = 1000


def quota_preflight(evidence, *, now):
    """Validate declared quota metadata only; never authenticates or authorizes transport."""
    if type(evidence) is not dict or set(evidence) != {"observed_utc", "daily_remaining", "minute_remaining", "plan"}:
        return False
    if evidence["plan"] != "FREE" or type(evidence["observed_utc"]) is not str:
        return False
    daily, minute = evidence["daily_remaining"], evidence["minute_remaining"]
    if type(daily) is not int or type(minute) is not int or not (2 <= daily <= 100 and 2 <= minute <= 10):
        return False
    try:
        observed = datetime.fromisoformat(evidence["observed_utc"].replace("Z", "+00:00"))
        if observed.tzinfo is None or now.tzinfo is None:
            return False
        return timedelta(0) <= now - observed <= timedelta(minutes=5)
    except (ValueError, TypeError, AttributeError, OverflowError):
        return False

def summarize(body):
    if type(body) is not dict or type(body.get("errors")) not in (dict, list) or body["errors"]:
        raise ValueError("PROVIDER_REJECTED")
    rows=body.get("response")
    if type(rows) is not list or len(rows)>MAX_ROWS:
        raise ValueError("BAD_ROWS")
    counts={}
    for row in rows:
        if type(row) is not dict:
            raise ValueError("BAD_ROW")
        f=row.get("fixture")
        if type(f) is not dict or type(f.get("id")) is not int or f["id"]<=0:
            raise ValueError("BAD_FIXTURE_ID")
        ident=f["id"]
        if ident in counts:
            raise ValueError("DUPLICATE_PROVIDER_ID")
        s=f.get("status")
        g=row.get("goals")
        if type(s) is not dict or type(s.get("short")) is not str or s["short"] not in LIVE:
            raise ValueError("UNEXPECTED_LIVE_STATUS")
        if type(g) is not dict or not all(type(g.get(k)) is int and 0<=g[k]<=30 for k in ("home","away")):
            raise ValueError("BAD_LIVE_SCORE")
        counts[ident]=True
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
    # Real transport intentionally disabled until trusted quota evidence and shared
    # consumer accounting exist. Injected requester is for offline tests only.
    if requester is None:
        out["reason"]="LIVE_TRANSPORT_DISABLED_PENDING_QUOTA_CONTROL"
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
