"""Bounded public OpenLigaDB Bundesliga schedule diagnostic, no raw output."""
import json
from collections import Counter
from datetime import timedelta
from urllib.error import HTTPError,URLError
from live_germany import read_json,API_BASE,iso
from live_core_same_batch_collection import clock
from team_identity import team_id

def project(payload,received):
    if received.tzinfo is None:raise ValueError("NAIVE_CLOCK")
    if not isinstance(payload,list) or len(payload)>30:raise ValueError("SCHEDULE_SHAPE")
    reasons=Counter();candidates=[];out=[]
    for r in payload:
        if not isinstance(r,dict):reasons["ROW_SHAPE"]+=1;continue
        if r.get("leagueShortcut")!="bl1":reasons["LEAGUE_MISMATCH"]+=1;continue
        if r.get("matchIsFinished") is not False:reasons["FINISHED_OR_STATUS_UNKNOWN"]+=1;continue
        if r.get("matchResults") not in (None,[]):reasons["RESULT_PRESENT"]+=1;continue
        try:ko=iso(r["matchDateTimeUTC"])
        except (ValueError,TypeError,KeyError,OverflowError):reasons["INVALID_UTC_FIELD"]+=1;continue
        if not received<ko<=received+timedelta(days=10):reasons["OUTSIDE_FUTURE_WINDOW"]+=1;continue
        h,a=(r.get("team1"),r.get("team2"))
        if not isinstance(h,dict) or not isinstance(a,dict):reasons["TEAM_IDENTITY_INVALID"]+=1;continue
        h,a=team_id("bundesliga",h.get("teamName")),team_id("bundesliga",a.get("teamName"))
        if not h or not a or h==a:reasons["TEAM_IDENTITY_INVALID"]+=1;continue
        ident=r.get("matchID")
        if type(ident) is not int or ident<=0:reasons["NATIVE_ID_INVALID"]+=1;continue
        candidates.append((ident,h,a,ko))
    ids=Counter(r[0] for r in candidates);keys=Counter(r[1:] for r in candidates)
    # Quarantine every occurrence of duplicate eligible native/natural IDs.
    for r in candidates:
        if ids[r[0]]!=1 or keys[r[1:]]!=1:
            reasons["DUPLICATE_CANDIDATE"]+=1;continue
        ident,h,a,ko=r
        reasons["ACCEPTED_LOCAL"]+=1
        out.append({"league":"bundesliga","home_id":h,"away_id":a,"native_id":str(ident),
                    "kickoff_utc":ko.isoformat(),"received_utc":received.isoformat()})
    if sum(reasons.values())!=len(payload):raise ValueError("ROW_DENOMINATOR")
    return out,{"returned_rows":len(payload),"disposition":dict(reasons),
            "local_scheduled_rows":reasons["ACCEPTED_LOCAL"]}

def inspect(payload,received):return project(payload,received)[1]

def capture(*,getter=read_json,now=clock):
    started=now();result=None;rows=[]
    try:
        body=getter(API_BASE+"bl1")
        received=now();rows,result=project(body,received);state="OK"
    except HTTPError as e:
        received=now();state="RATE_LIMITED" if e.code==429 else "HTTP_ERROR"
    except (URLError,OSError,TimeoutError):
        received=now();state="NETWORK_ERROR"
    except (ValueError,TypeError,KeyError,OverflowError):
        received=now();state="INVALID_DATA"
    return rows,{"provider":"OpenLigaDB","league":"bundesliga","requests_attempted":1,
            "response_status":state,"schedule_diagnostic":result,"started_utc":started.isoformat(),
            "received_utc":received.isoformat(),"community_source_not_official":True,
            "native_clock_attested":False,"same_event_cross_source_join_verified":False,
            "authenticated_forward_samples":0,"production_recommendations":"DISABLED","status":"HOLD"}
def probe(*,getter=read_json,now=clock):return capture(getter=getter,now=now)[1]
if __name__=="__main__":print(json.dumps(probe(),sort_keys=True,allow_nan=False))
