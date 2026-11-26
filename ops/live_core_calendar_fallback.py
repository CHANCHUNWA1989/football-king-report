"""Public CC0 calendar-only coverage check, not a UTC schedule source."""
import json
from datetime import date,timedelta
from collections import Counter
from urllib.error import HTTPError,URLError
from wide_sources import UPSTREAM,request_json
from live_core_same_batch_collection import clock
from team_identity import team_id
FILES={"epl":"en.1","championship":"en.2","laliga":"es.1","seriea":"it.1","ligue1":"fr.1"}
def inspect(league,doc,day):
    if not isinstance(doc,dict) or not isinstance(doc.get("matches"),list) or len(doc["matches"])>1600:raise ValueError("CALENDAR_SHAPE")
    c=Counter();keys=Counter()
    for r in doc["matches"]:
        if not isinstance(r,dict):c["INVALID"]+=1;continue
        try:d=date.fromisoformat(r["date"])
        except (KeyError,ValueError,TypeError):c["INVALID"]+=1;continue
        if not day<=d<=day+timedelta(days=10):c["OUTSIDE_WINDOW"]+=1;continue
        if "score" in r and r["score"] not in (None,{}):c["SCORE_PRESENT_OR_PLACEHOLDER"]+=1;continue
        h,a=team_id(league,r.get("team1")),team_id(league,r.get("team2"))
        if not h or not a or h==a:c["INVALID"]+=1;continue
        keys[(d,h,a)]+=1
    for n in keys.values():c["UNIQUE_CALENDAR_CANDIDATE" if n==1 else "DUPLICATE_CALENDAR_CANDIDATE"]+=n
    if sum(c.values())!=len(doc["matches"]):raise ValueError("CALENDAR_DENOMINATOR")
    return {"returned_rows":len(doc["matches"]),"disposition":dict(c),"calendar_candidates":c["UNIQUE_CALENDAR_CANDIDATE"],"precise_utc_fixtures":0}
def probe(*,getter=request_json,now=clock):
    t=now();reports={};n=0
    # Fixed season and path; do not turn unzoned local time into UTC.
    for k,f in FILES.items():
        n+=1
        try:reports[k]={"status":"OK",**inspect(k,getter(UPSTREAM+"2026-27/"+f+".json"),t.date())}
        except HTTPError as e:
            reports[k]={"status":"RATE_LIMITED" if e.code==429 else "HTTP_ERROR","http_code":e.code}
            if e.code==429:break
        except (URLError,OSError,TimeoutError):reports[k]={"status":"NETWORK_ERROR"}
        except (ValueError,TypeError,KeyError,OverflowError):reports[k]={"status":"INVALID_DATA"}
    return {"public_calendar_probe":True,"checked_utc":now().isoformat(),"requests_attempted":n,"by_league":reports,
            "calendar_only":True,"native_observation_clock_attested":False,"authenticated_forward_samples":0,"production_recommendations":"DISABLED","status":"HOLD"}
if __name__=="__main__":print(json.dumps(probe(),sort_keys=True,allow_nan=False))
