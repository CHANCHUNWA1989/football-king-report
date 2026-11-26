"""Same-process market/schedule collection; counts only, no raw prices.
Existing PropLine budget unchanged; at most six additional public next-league
schedule requests. No claim of independent upstream feeds or executable odds.
"""
import argparse
import json
import re
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

def schedule_diagnostic(body,league,received):
    if received.tzinfo is None:raise ValueError("NAIVE_CLOCK")
    if not isinstance(body,dict) or "events" not in body:raise ValueError("SCHEDULE_SHAPE")
    rows=body["events"]
    if rows is None:rows=[]
    if not isinstance(rows,list) or len(rows)>30:raise ValueError("SCHEDULE_SHAPE")
    out=[];reasons=Counter()
    # Preserve the existing free next-league first-event limit.
    for r in rows[:1]:
        if not isinstance(r,dict):reasons["ROW_SHAPE"]+=1;continue
        if str(r.get("idLeague"))!=str(SD_BD[league]):reasons["LEAGUE_MISMATCH"]+=1;continue
        status=str(r.get("strStatus","")).strip().casefold()
        if not status or status=="none":reasons["STATUS_MISSING"]+=1;continue
        if status not in ("not started","scheduled","ns"):reasons["STATUS_NOT_EXPLICIT_SCHEDULED"]+=1;continue
        if r.get("intHomeScore") is not None or r.get("intAwayScore") is not None:reasons["SCORE_PRESENT"]+=1;continue
        raw_time=r.get("strTimestamp")
        if raw_time is None or raw_time=="":reasons["KICKOFF_MISSING"]+=1;continue
        if type(raw_time) is not str:reasons["KICKOFF_INVALID"]+=1;continue
        try:
            parsed=datetime.fromisoformat(raw_time.replace("Z","+00:00"))
        except (TypeError,ValueError,OverflowError):
            reasons["KICKOFF_INVALID"]+=1;continue
        if parsed.tzinfo is None:
            reasons["KICKOFF_NAIVE"]+=1;continue
        ko=parsed.astimezone(timezone.utc)
        h,a=team_id(league,r.get("strHomeTeam")),team_id(league,r.get("strAwayTeam"))
        eid=r.get("idEvent")
        if not h or not a or h==a:reasons["TEAM_IDENTITY_INVALID"]+=1;continue
        if type(eid) not in (str,int) or not str(eid).strip():reasons["NATIVE_ID_INVALID"]+=1;continue
        if ko<=received:reasons["KICKOFF_NOT_FUTURE"]+=1;continue
        out.append({"league":league,"home_id":h,"away_id":a,"native_id":str(eid),
                    "kickoff_utc":ko.isoformat(),"received_utc":received.isoformat()})
        reasons["ACCEPTED_LOCAL"]+=1
    if sum(reasons.values())!=min(1,len(rows)):raise ValueError("SCHEDULE_DENOMINATOR")
    return out,{"returned_rows":len(rows),"inspected_rows":min(1,len(rows)),
                "not_inspected_free_limit":max(0,len(rows)-1),"disposition":dict(reasons)}

def schedule_rows(body,league,received):
    return schedule_diagnostic(body,league,received)[0]

def naive_utc_candidate(body,received):
    """German first-row research only. No blanket timezone assumption."""
    _,d=schedule_diagnostic(body,"bundesliga",received)
    if d["disposition"]!={"KICKOFF_NAIVE":1}:return [],"NOT_NAIVE_ELIGIBLE"
    r=body["events"][0]
    raw,day,t=r.get("strTimestamp"),r.get("dateEvent"),r.get("strTime")
    if not all(type(v) is str for v in (raw,day,t)):
        return [],"UTC_FIELDS_MISSING"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",raw) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",day) or not re.fullmatch(r"\d{2}:\d{2}:\d{2}",t):
        return [],"UTC_FIELDS_FORMAT"
    if raw!=day+"T"+t:return [],"UTC_FIELDS_CONFLICT"
    if t=="00:00:00":return [],"MIDNIGHT_PLACEHOLDER_RISK"
    rows,_=schedule_diagnostic({"events":[dict(r,strTimestamp=raw+"Z")]},"bundesliga",received)
    return rows,"UTC_CANDIDATE_NOT_ATTESTED" if rows else "NORMALIZED_ROW_REJECTED"

def collect_schedules(*,fetcher=secondary_fetch,now=clock,pause=time.sleep,naive_sink=None,attempt_sink=None):
    out=[];attempted=0;failures=Counter()
    for league,ident in SD_BD.items():
        if attempted>=MAX_SCHEDULE_CALLS:break
        if attempted:pause(SPORTSDB_MIN_START_INTERVAL_SECONDS)
        attempted+=1
        body,state=fetcher("thesportsdb",f"https://www.thesportsdb.com/api/v1/json/123/eventsnextleague.php?id={ident}",{})
        received=now()
        attempt={"league":league,"response_status":state if state in ("OK","RATE_LIMITED","KEY_REJECTED","PLAN_OR_LEAGUE_RESTRICTED","HTTP_ERROR","NETWORK_ERROR","INVALID_DATA") else "OTHER_ERROR",
                 "received_utc":received.isoformat(),"accepted_rows":0,"diagnostic":None}
        if attempt_sink is not None:attempt_sink.append(attempt)
        if state!="OK":
            failures[state if state in ("RATE_LIMITED","KEY_REJECTED","PLAN_OR_LEAGUE_RESTRICTED","HTTP_ERROR","NETWORK_ERROR","INVALID_DATA") else "OTHER_ERROR"]+=1
            if state in ("RATE_LIMITED","KEY_REJECTED","PLAN_OR_LEAGUE_RESTRICTED"):break
            continue
        try:
            accepted,diag=schedule_diagnostic(body,league,received)
            out.extend(accepted)
            attempt["accepted_rows"]=len(accepted)
            attempt["diagnostic"]=diag
            if naive_sink is not None and league=="bundesliga":
                candidates,reason=naive_utc_candidate(body,received)
                naive_sink.extend(candidates)
                if reason not in ("NOT_NAIVE_ELIGIBLE","UTC_CANDIDATE_NOT_ATTESTED"):failures[reason]+=1
            if not diag["inspected_rows"]:failures["EMPTY_SCHEDULE_RESPONSE"]+=1
            for reason,n in diag["disposition"].items():
                if reason!="ACCEPTED_LOCAL":failures[reason]+=n
        except (ValueError,TypeError,OverflowError):
            attempt["response_status"]="INVALID_DATA"
            failures["INVALID_DATA"]+=1
    return out,attempted,dict(failures)

def reconcile_projection(six,markets):
    """Check the ephemeral complete-market subset against its own collector.
    Marginals bound the subset but cannot identify individual fixtures."""
    projected=Counter(r["league"] for r in markets)
    if set(projected)-set(LEAGUES):raise ValueError("PROJECTION_LEAGUE")
    result={}
    for row in six["coverage"]:
        league=row["league"];n=row["utc_identity_events"]
        values=[row[k] for k in ("full_1x2_events","paired_spread_events","paired_totals_events")]
        if (type(n) is not int or n<0 or n>row["upcoming_events"]
                or any(type(v) is not int or not 0<=v<=n for v in values)):
            raise ValueError("PROJECTION_MARGINAL")
        lo,hi=max(0,sum(values)-2*n),min(values)
        observed=projected[league]
        if not lo<=observed<=hi:raise ValueError("PROJECTION_ACCOUNTING")
        result[league]={"complete_market_projection_count":observed,
                        "marginal_intersection_bounds":[lo,hi]}
    return result

def validate_projection(rows,limit,*,market=False):
    if not isinstance(rows,list) or len(rows)>limit:raise ValueError("ROW_BOUND")
    expected={"league","home_id","away_id","native_id","kickoff_utc","received_utc"}
    if market:expected.add("oldest_market_update_utc")
    for row in rows:
        if not isinstance(row,dict) or set(row)!=expected or row["league"] not in LEAGUES:
            raise ValueError("PROJECTION_SCOPE")
        if (any(type(row[k]) is not str or not row[k].strip() or len(row[k])>200
                for k in ("home_id","away_id","native_id"))
                or row["home_id"]==row["away_id"]):
            raise ValueError("PROJECTION_IDENTITY")
        if stamp(row["kickoff_utc"])<=stamp(row["received_utc"]):
            raise ValueError("PROJECTION_CLOCK")

def compare_batch(markets,schedules,*,finished,requests,failures):
    if finished.tzinfo is None:raise ValueError("NAIVE_CLOCK")
    if type(requests) is not int or not 0<=requests<=MAX_SCHEDULE_CALLS:raise ValueError("SCHEDULE_BUDGET")
    validate_projection(markets,960,market=True)
    validate_projection(schedules,MAX_SCHEDULE_CALLS)
    if len(schedules)>requests:raise ValueError("SCHEDULE_REQUEST_ACCOUNTING")
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
    reasons={k:Counter() for k in LEAGUES}
    for r in markets:
        b=by[r["league"]];b["market_events"]+=1
        ko=stamp(r["kickoff_utc"]);at=stamp(r["received_utc"])
        why=reasons[r["league"]]
        updated=stamp(r["oldest_market_update_utc"])
        if not out["market_fresh"]:
            why["BATCH_RECEIPT_STALE_OR_FUTURE"]+=1;continue
        if not at<=finished<ko-timedelta(minutes=10):
            why["PREMATCH_CUTOFF"]+=1;continue
        # Conservative: oldest complete market block seen, even if a later
        # duplicate disqualified that block. Never rejuvenate quote clocks.
        if not timedelta(0)<=at-updated<=MAX_BATCH_AGE or not timedelta(0)<=finished-updated<=MAX_BATCH_AGE:
            why["MARKET_UPDATE_STALE_OR_FUTURE"]+=1;continue
        if mi[r["native_id"]]!=1 or natural[(ident(r),ko)]!=1:
            b["ambiguous_or_duplicate_source_events"]+=1
            why["MARKET_ID_AMBIGUOUS"]+=1;continue
        b["time_valid_market_events"]+=1
        if not out["secondary_fresh"]:
            why["SECONDARY_UNAVAILABLE_OR_STALE"]+=1;continue
        candidates=groups.get(ident(r),[])
        if len(candidates)>1 or any(si[x["native_id"]]!=1 for x in candidates):
            b["ambiguous_or_duplicate_source_events"]+=1
            why["SECONDARY_ID_AMBIGUOUS"]+=1;continue
        if len(candidates)==1:
            c=candidates[0]
            if stamp(c["kickoff_utc"])==ko:
                b["one_other_publisher_agreements"]+=1
                why["SCHEDULE_AGREEMENT_UNAUTHENTICATED"]+=1
            else:
                b["other_publisher_conflicts"]+=1
                why["KICKOFF_CONFLICT"]+=1
        else:why["NO_SCHEDULE_MATCH"]+=1
    for b in out["by_league"]:
        b["unmatched_or_unverified_market_events"]=b["time_valid_market_events"]-b["one_other_publisher_agreements"]
        for a,k in (("time_valid_market_count","time_valid_market_events"),
                    ("at_least_one_other_publisher_agreement","one_other_publisher_agreements"),
                    ("source_schedule_conflict_observations","other_publisher_conflicts"),
                    ("ambiguous_or_duplicate_source_event_observations","ambiguous_or_duplicate_source_events")):
            out[a]+=b[k]
    for league,b in by.items():
        if sum(reasons[league].values())!=b["market_events"]:
            raise ValueError("REJECTION_PARTITION_MISMATCH")
    out["market_row_disposition_by_league"]={k:dict(v) for k,v in reasons.items()}
    out["market_row_disposition"] = dict(sum(reasons.values(),Counter()))
    out["market_update_age_checked_at_batch_finish"]=True
    if out["time_valid_market_count"] and out["secondary_fresh"]:out["status"]="RESEARCH_ONLY"
    validate_overlap(out)
    return out

def run(*,token=None,market_fetcher=market_fetch,schedule_fetcher=secondary_fetch,now=clock,pause=time.sleep,settled=None,fixed_now=None,openliga_getter=None,football_data_token=None,football_data_fetcher=None):
    market_rows=[]
    six=collect(token=token,now=fixed_now,fetcher=market_fetcher,identity_sink=market_rows)
    naive=[];attempts=[]
    schedules,requests,failures=collect_schedules(fetcher=schedule_fetcher,now=now,pause=pause,naive_sink=naive if openliga_getter is not None else None,attempt_sink=attempts) if market_rows else ([],0,{})
    # CLI explicitly opts into one extra no-key request; injected offline
    # callers remain network-free unless they supply their own getter.
    german_rows=[];german_capture=None
    if openliga_getter is not None and any(r["league"]=="bundesliga" for r in market_rows):
        from live_core_openliga_schedule_smoke import capture
        german_rows,german_capture=capture(getter=openliga_getter,now=now)
    from live_core_football_data_schedule import collect as collect_fd,review as review_fd
    fd_rows=[];fd_capture=None
    if football_data_token and market_rows:
        fd_rows,fd_capture=collect_fd([k for k in LEAGUES if any(r["league"]==k for r in market_rows)],token=football_data_token,
                                    fetcher=football_data_fetcher or secondary_fetch,now=now,pause=pause)
    finished=now()
    six["captured_utc"]=finished.isoformat()
    validate_market(six,now=finished)
    projection=reconcile_projection(six,market_rows)
    overlap=compare_batch(market_rows,schedules,finished=finished,requests=requests,failures=failures)
    overlap["same_collector_projection_accounting"]=projection
    overlap["complete_market_projection_count"]=len(market_rows)
    overlap["projection_counts_not_authenticated_fixtures"]=True
    from live_core_german_schedule_corroboration import review,confirm_naive
    overlap["german_schedule_research"]=review(market_rows,schedules,german_rows,finished=finished)
    confirmed,tz_report=confirm_naive(naive,german_rows,finished=finished)
    overlap["timezone_candidate_review"]=tz_report
    overlap["german_timezone_candidate_market_research"]=review(market_rows,confirmed,german_rows,finished=finished)
    overlap["german_schedule_capture"]=german_capture
    overlap["openliga_requests_attempted"]=int(german_capture is not None)
    overlap["public_schedule_total_request_budget"]=7
    overlap["football_data_schedule_capture"]=fd_capture
    overlap["football_data_schedule_research"]=review_fd(market_rows,fd_rows,finished=finished)
    overlap["optional_credentialed_schedule_request_budget"]=6
    from live_core_schedule_resilience import route_batch
    overlap["schedule_resilience"]=route_batch(market_rows,schedules,german_rows,attempts,requests,german_capture,finished=finished)
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
    import os
    from live_germany import read_json
    results=run(settled=load(a.settled),openliga_getter=read_json,football_data_token=os.environ.get("FOOTBALL_DATA_ORG_TOKEN",""))
    for name,obj in zip(("six-free.json","fixture-overlap.json","seven-gates.json"),results):
        with Path(name).open("x",encoding="utf-8") as f:json.dump(obj,f,sort_keys=True,allow_nan=False)
    print(json.dumps({"status":"HOLD","schedule_requests":results[1]["schedule_requests_attempted"],
                      "schedule_agreements":results[1]["at_least_one_other_publisher_agreement"],
                      "production_recommendations":"DISABLED"}))
if __name__=="__main__":main()
