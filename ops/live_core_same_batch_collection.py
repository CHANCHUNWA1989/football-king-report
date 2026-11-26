"""Same-process market/schedule collection; counts only, no raw prices.
Existing PropLine budget unchanged; at most six additional public next-league
schedule requests. No claim of independent upstream feeds or executable odds.
"""
import argparse
import json
import time
from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
from pathlib import Path
from six_league_free_upgrade import collect,validate as validate_market,audit,fetch as market_fetch,load
from six_league_fixture_overlap import SCHEMA,LEAGUES,_row_report,validate as validate_overlap,stamp
from secondary_sources import fetch as secondary_fetch,SD_BD,SPORTSDB_MIN_START_INTERVAL_SECONDS
from team_identity import team_id

MAX_SCHEDULE_CALLS=6
MAX_BATCH_AGE=timedelta(minutes=20)
def clock():return datetime.now(timezone.utc)

def schedule_rows(body,league,received):
    rows=body.get("events") if isinstance(body,dict) else None
    if rows is None:return []
    if not isinstance(rows,list) or len(rows)>30:raise ValueError("SCHEDULE_SHAPE")
    out=[]
    # Existing free next-league scope permits only the first event; never
    # treat missing or unknown status as scheduled.
    for r in rows[:1]:
        if not isinstance(r,dict) or str(r.get("idLeague"))!=str(SD_BD[league]):continue
        if str(r.get("strStatus","")).strip().casefold() not in ("not started","scheduled","ns"):continue
        if r.get("intHomeScore") is not None or r.get("intAwayScore") is not None:continue
        try:ko=stamp(r["strTimestamp"])
        except (KeyError,TypeError,ValueError):continue
        h,a=team_id(league,r.get("strHomeTeam")),team_id(league,r.get("strAwayTeam"))
        eid=r.get("idEvent")
        if not h or not a or h==a or type(eid) not in (str,int) or not str(eid).strip() or ko<=received:continue
        out.append({"league":league,"home_id":h,"away_id":a,"native_id":str(eid),
                    "kickoff_utc":ko.isoformat(),"received_utc":received.isoformat()})
    return out

def collect_schedules(*,fetcher=secondary_fetch,now=clock,pause=time.sleep):
    out=[];attempted=0;failures=Counter()
    for league,ident in SD_BD.items():
        if attempted:pause(SPORTSDB_MIN_START_INTERVAL_SECONDS)
        attempted+=1
        body,state=fetcher("thesportsdb",f"https://www.thesportsdb.com/api/v1/json/123/eventsnextleague.php?id={ident}",{})
        received=now()
        if state!="OK":
            failures[state if state in ("RATE_LIMITED","KEY_REJECTED","PLAN_OR_LEAGUE_RESTRICTED","HTTP_ERROR","NETWORK_ERROR","INVALID_DATA") else "OTHER_ERROR"]+=1
            if state in ("RATE_LIMITED","KEY_REJECTED","PLAN_OR_LEAGUE_RESTRICTED"):break
            continue
        try:out.extend(schedule_rows(body,league,received))
        except (ValueError,TypeError):failures["INVALID_DATA"]+=1
    return out,attempted,dict(failures)

def compare_batch(markets,schedules,*,finished,requests,failures):
    if finished.tzinfo is None:raise ValueError("NAIVE_CLOCK")
    if not 0<=requests<=MAX_SCHEDULE_CALLS:raise ValueError("SCHEDULE_BUDGET")
    if len(markets)>960 or len(schedules)>6:raise ValueError("ROW_BOUND")
    out={"schema":SCHEMA,"captured_utc":finished.isoformat(),"status":"HOLD",
         "market_as_of_utc":max((stamp(r["received_utc"]) for r in markets),default=None),
         "secondary_as_of_utc":max((stamp(r["received_utc"]) for r in schedules),default=None),
         "market_fresh":False,"secondary_fresh":False,"secondary_licensed_source_validation":False,
         "by_league":[_row_report(l) for l in LEAGUES],"market_sample_count":len(markets),
         "time_valid_market_count":0,"at_least_one_other_publisher_agreement":0,
         "at_least_two_other_publisher_agreements":0,"source_schedule_conflict_observations":0,
         "ambiguous_or_duplicate_source_event_observations":0,"independently_verified_final_results":0,
         "other_publisher_not_independent_bookmaker":True,"same_upstream_feed_not_ruled_out":True,
         "all_six_leagues_independently_verified":False,"original_bookmaker_quotes_stored":False,
         "model_promotion_authorized":False,"production_recommendations":"DISABLED",
         "same_process_collection":True,"schedule_requests_attempted":requests,"schedule_request_budget":6,
         "schedule_failures":failures,"native_observation_clocks_attested":False,
         "canonical_identity_authenticated":False}
    for label,rs in (("market",markets),("secondary",schedules)):
        out[label+"_fresh"]=bool(rs) and all(timedelta(0)<=finished-stamp(r["received_utc"])<=MAX_BATCH_AGE for r in rs)
        k=label+"_as_of_utc";out[k]=out[k].isoformat() if out[k] else None
    def ident(r):return (r["league"],r["home_id"],r["away_id"])
    mi=Counter(r["native_id"] for r in markets);si=Counter(r["native_id"] for r in schedules)
    groups=defaultdict(list)
    for r in schedules:groups[ident(r)].append(r)
    natural=Counter((ident(r),stamp(r["kickoff_utc"])) for r in markets)
    by={r["league"]:r for r in out["by_league"]}
    for r in markets:
        b=by[r["league"]];b["market_events"]+=1
        ko=stamp(r["kickoff_utc"]);at=stamp(r["received_utc"])
        if not out["market_fresh"] or not at<=finished<ko-timedelta(minutes=10):continue
        if mi[r["native_id"]]!=1 or natural[(ident(r),ko)]!=1:
            b["ambiguous_or_duplicate_source_events"]+=1;continue
        b["time_valid_market_events"]+=1
        if not out["secondary_fresh"]:continue
        candidates=groups.get(ident(r),[])
        if len(candidates)>1 or any(si[x["native_id"]]!=1 for x in candidates):
            b["ambiguous_or_duplicate_source_events"]+=1;continue
        if len(candidates)==1:
            c=candidates[0]
            if stamp(c["kickoff_utc"])==ko:
                b["one_other_publisher_agreements"]+=1
            else:b["other_publisher_conflicts"]+=1
    for b in out["by_league"]:
        b["unmatched_or_unverified_market_events"]=b["time_valid_market_events"]-b["one_other_publisher_agreements"]
        for a,k in (("time_valid_market_count","time_valid_market_events"),
                    ("at_least_one_other_publisher_agreement","one_other_publisher_agreements"),
                    ("source_schedule_conflict_observations","other_publisher_conflicts"),
                    ("ambiguous_or_duplicate_source_event_observations","ambiguous_or_duplicate_source_events")):
            out[a]+=b[k]
    if out["market_fresh"] and out["secondary_fresh"]:out["status"]="RESEARCH_ONLY"
    validate_overlap(out)
    return out

def run(*,token=None,market_fetcher=market_fetch,schedule_fetcher=secondary_fetch,now=clock,pause=time.sleep,settled=None,fixed_now=None):
    market_rows=[]
    six=collect(token=token,now=fixed_now,fetcher=market_fetcher,identity_sink=market_rows)
    schedules,requests,failures=collect_schedules(fetcher=schedule_fetcher,now=now,pause=pause) if market_rows else ([],0,{})
    finished=now()
    six["captured_utc"]=finished.isoformat()
    validate_market(six,now=finished)
    overlap=compare_batch(market_rows,schedules,finished=finished,requests=requests,failures=failures)
    # Do not pass the old market/latest.json or stale sources/latest.json to
    # the gate. Same-run counts are explicitly separate from native attestation.
    gates=audit(six,market=None,sources=None,settled=settled,fixture_audit=overlap,now=finished)
    for check in gates["checks"]:
        if check["key"]=="utc_fixture_identity":
            check["evidence"]=f'{overlap["time_valid_market_count"]} same-run market rows; {overlap["at_least_one_other_publisher_agreement"]} schedule agreements; canonical identities not authenticated'
        elif check["key"]=="sealed_point_in_time":
            check["evidence"]="Same-process collection envelope clocks only; no immutable pre-kickoff feature attestation"
    return six,overlap,gates

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--settled",default="evidence/settled.json")
    a=p.parse_args()
    results=run(settled=load(a.settled))
    for name,obj in zip(("six-free.json","fixture-overlap.json","seven-gates.json"),results):
        with Path(name).open("x",encoding="utf-8") as f:json.dump(obj,f,sort_keys=True,allow_nan=False)
    print(json.dumps({"status":"HOLD","schedule_requests":results[1]["schedule_requests_attempted"],
                      "schedule_agreements":results[1]["at_least_one_other_publisher_agreement"],
                      "production_recommendations":"DISABLED"}))
if __name__=="__main__":main()
