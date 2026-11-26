"""Per-league schedule availability and attempt accounting. No evidence admission."""
from collections import Counter
from datetime import timedelta
from live_core_same_batch_collection import LEAGUES,stamp,validate_projection,MAX_BATCH_AGE

STATES={"OK","RATE_LIMITED","KEY_REJECTED","PLAN_OR_LEAGUE_RESTRICTED","HTTP_ERROR","NETWORK_ERROR","INVALID_DATA","OTHER_ERROR"}
STOP={"RATE_LIMITED","KEY_REJECTED","PLAN_OR_LEAGUE_RESTRICTED"}

def route_batch(markets,sports,openliga,attempts,requests,german_capture,*,finished):
    if finished.tzinfo is None:raise ValueError("NAIVE_CLOCK")
    validate_projection(markets,960,market=True);validate_projection(sports,6);validate_projection(openliga,30)
    if type(requests) is not int or not 0<=requests<=6 or len(attempts)!=requests:raise ValueError("ATTEMPT_DENOMINATOR")
    if any(r["league"]!="bundesliga" for r in openliga):raise ValueError("OPENLIGA_SCOPE")
    if german_capture is None and openliga:raise ValueError("UNRECORDED_OPENLIGA")
    if german_capture is not None:
        if german_capture.get("requests_attempted")!=1:raise ValueError("OPENLIGA_REQUEST_COUNT")
        diag=german_capture.get("schedule_diagnostic")
        if len(openliga)!=(diag.get("local_scheduled_rows",0) if isinstance(diag,dict) else 0):raise ValueError("OPENLIGA_ROW_COUNT")
    by={};stop=False;last=None;observed=Counter(r["league"] for r in sports)
    for a in attempts:
        if set(a)!={"league","response_status","received_utc","accepted_rows","diagnostic"}:raise ValueError("ATTEMPT_SCHEMA")
        k=a["league"];t=stamp(a["received_utc"]);state=a["response_status"]
        if k not in LEAGUES or k in by or stop or state not in STATES or t>finished or (last is not None and t<last):raise ValueError("ATTEMPT_ORDER_OR_CLOCK")
        if type(a["accepted_rows"]) is not int or a["accepted_rows"]!=observed[k] or a["accepted_rows"]>1:raise ValueError("ATTEMPT_ROWS")
        if state!="OK" and a["accepted_rows"]:raise ValueError("FAILED_WITH_ROWS")
        by[k]=a;stop=state in STOP;last=t
    if set(observed)-set(by):raise ValueError("UNRECORDED_SPORTSDB")
    def fresh(r):return timedelta(0)<=finished-stamp(r["received_utc"])<=MAX_BATCH_AGE and stamp(r["kickoff_utc"])>finished
    def eligible(rows):
        ids=Counter(r["native_id"] for r in rows)
        keys=Counter((r["league"],r["home_id"],r["away_id"],stamp(r["kickoff_utc"])) for r in rows)
        return [r for r in rows if fresh(r) and ids[r["native_id"]]==1 and keys[(r["league"],r["home_id"],r["away_id"],stamp(r["kickoff_utc"]))]==1]
    sf,of=eligible(sports),eligible(openliga)
    report={}
    for k in LEAGUES:
        p=by.get(k)
        s=[r for r in sf if r["league"]==k];o=[r for r in of if r["league"]==k]
        n=sum(r["league"]==k for r in markets)
        if s and o:route="BOTH_SOURCES_AVAILABLE_NOT_CORROBORATED"
        elif s:route="SPORTSDB_SCHEDULE_ONLY"
        elif o:route="OPENLIGA_FALLBACK_SCHEDULE_ONLY"
        else:route="NO_FRESH_SCHEDULE_ROWS"
        report[k]={"market_projection_rows":n,"sportsdb_attempt_status":p["response_status"] if p else ("NOT_REQUESTED_AFTER_PROVIDER_STOP" if stop else "NOT_REQUESTED"),
                   "sportsdb_accepted_rows":observed[k],"sportsdb_fresh_unique_rows":len(s),"openliga_fresh_unique_rows":len(o),
                   "route":route,"schedule_only":True,"authenticated_forward_samples":0}
    return {"by_league":report,"sportsdb_requests_attempted":requests,"openliga_requests_attempted":int(german_capture is not None),
            "provider_stop_observed":stop,"fresh_schedule_leagues":sum(v["route"]!="NO_FRESH_SCHEDULE_ROWS" for v in report.values()),
            "source_availability_not_event_agreement":True,"executable_odds_fallback_available":False,
            "authenticated_forward_samples":0,"production_recommendations":"DISABLED","status":"HOLD"}
