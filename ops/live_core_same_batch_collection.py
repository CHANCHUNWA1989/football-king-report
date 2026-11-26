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

def collect_schedules(*,fetcher=secondary_fetch,now=clock,pause=time.sleep,diagnostics=None,row_diagnostics=None,naive_sink=None,candidate_diagnostic=None,attempt_sink=None):
    out=[];attempted=0;failures=Counter()
    details={l:"NOT_ATTEMPTED" for l in LEAGUES}
    if diagnostics is not None:diagnostics.update(details)
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
            reason=state if state in ("RATE_LIMITED","KEY_REJECTED","PLAN_OR_LEAGUE_RESTRICTED","HTTP_ERROR","NETWORK_ERROR","INVALID_DATA") else "OTHER_ERROR"
            failures[reason]+=1
            details[league]=reason
            if diagnostics is not None:diagnostics[league]=reason
            if state in ("RATE_LIMITED","KEY_REJECTED","PLAN_OR_LEAGUE_RESTRICTED"):break
            continue
        try:
            found,diag=schedule_diagnostic(body,league,received)
            # Commit the strict row only after all optional parsing succeeds.
            if naive_sink is not None and league=="bundesliga":
                candidates,reason=naive_utc_candidate(body,received)
                naive_sink.extend(candidates)
                if candidate_diagnostic is not None:candidate_diagnostic["reason"]=reason
            out.extend(found)
            attempt["accepted_rows"]=len(found)
            attempt["diagnostic"]=diag
            details[league]="SAMPLED" if found else "NO_ELIGIBLE_FIRST_EVENT"
            if row_diagnostics is not None:row_diagnostics[league]=diag
            if not diag["inspected_rows"]:failures["EMPTY_SCHEDULE_RESPONSE"]+=1
            for reason,n in diag["disposition"].items():
                if reason!="ACCEPTED_LOCAL":failures[reason]+=n
        except (ValueError,TypeError,OverflowError):
            failures["INVALID_DATA"]+=1
            attempt["response_status"]="INVALID_DATA"
            details[league]="INVALID_DATA"
        if diagnostics is not None:diagnostics[league]=details[league]
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
    pair_counts=Counter(ident(r) for r in markets)
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
        if mi[r["native_id"]]!=1 or natural[(ident(r),ko)]!=1 or pair_counts[ident(r)]!=1:
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
    validate_dispositions(out)
    if out["time_valid_market_count"] and out["secondary_fresh"]:out["status"]="RESEARCH_ONLY"
    validate_overlap(out)
    return out

def validate_dispositions(out):
    """Cross-check all published rejection counts, not upstream authenticity."""
    allowed={"BATCH_RECEIPT_STALE_OR_FUTURE","PREMATCH_CUTOFF","MARKET_UPDATE_STALE_OR_FUTURE",
             "MARKET_ID_AMBIGUOUS","SECONDARY_UNAVAILABLE_OR_STALE","SECONDARY_ID_AMBIGUOUS",
             "SCHEDULE_AGREEMENT_UNAUTHENTICATED","KICKOFF_CONFLICT","NO_SCHEDULE_MATCH"}
    valid={"SECONDARY_UNAVAILABLE_OR_STALE","SECONDARY_ID_AMBIGUOUS",
           "SCHEDULE_AGREEMENT_UNAUTHENTICATED","KICKOFF_CONFLICT","NO_SCHEDULE_MATCH"}
    groups=out["market_row_disposition_by_league"]
    if set(groups)!=set(LEAGUES):raise ValueError("DISPOSITION_LEAGUES")
    total=Counter()
    for row in out["by_league"]:
        d=groups[row["league"]]
        if not isinstance(d,dict) or set(d)-allowed or any(type(v) is not int or v<0 for v in d.values()):
            raise ValueError("DISPOSITION_SCOPE")
        if (sum(d.values())!=row["market_events"]
                or sum(d.get(k,0) for k in valid)!=row["time_valid_market_events"]
                or d.get("SCHEDULE_AGREEMENT_UNAUTHENTICATED",0)!=row["one_other_publisher_agreements"]
                or d.get("KICKOFF_CONFLICT",0)!=row["other_publisher_conflicts"]
                or d.get("MARKET_ID_AMBIGUOUS",0)+d.get("SECONDARY_ID_AMBIGUOUS",0)!=row["ambiguous_or_duplicate_source_events"]):
            raise ValueError("DISPOSITION_LEAGUE_ACCOUNTING")
        total.update(d)
    if dict(total)!=out["market_row_disposition"] or sum(total.values())!=out["market_sample_count"]:
        raise ValueError("DISPOSITION_TOTAL_ACCOUNTING")
    if (sum(total[k] for k in valid)!=out["time_valid_market_count"]
            or total["SCHEDULE_AGREEMENT_UNAUTHENTICATED"]!=out["at_least_one_other_publisher_agreement"]
            or total["KICKOFF_CONFLICT"]!=out["source_schedule_conflict_observations"]
            or total["MARKET_ID_AMBIGUOUS"]+total["SECONDARY_ID_AMBIGUOUS"]!=out["ambiguous_or_duplicate_source_event_observations"]):
        raise ValueError("DISPOSITION_GLOBAL_ACCOUNTING")
    return True

def run(*,token=None,market_fetcher=market_fetch,schedule_fetcher=secondary_fetch,now=clock,pause=time.sleep,settled=None,fixed_now=None,openliga_getter=None):
    market_rows=[]
    six=collect(token=token,now=fixed_now,fetcher=market_fetcher,identity_sink=market_rows)
    details={l:"NOT_ATTEMPTED_NO_MARKET_PROJECTION" for l in LEAGUES}
    row_diagnostics={}
    naive=[];candidate_diag={};attempts=[]
    german_requested=openliga_getter is not None and any(r["league"]=="bundesliga" for r in market_rows)
    schedules,requests,failures=collect_schedules(fetcher=schedule_fetcher,now=now,pause=pause,diagnostics=details,row_diagnostics=row_diagnostics,naive_sink=naive if german_requested else None,candidate_diagnostic=candidate_diag,attempt_sink=attempts) if market_rows else ([],0,{})
    # CLI explicitly opts into one extra no-key request; injected offline
    # callers remain network-free unless they supply their own getter.
    german_rows=[];german_capture=None
    if german_requested:
        from live_core_openliga_schedule_smoke import capture
        german_rows,german_capture=capture(getter=openliga_getter,now=now)
    finished=now()
    six["captured_utc"]=finished.isoformat()
    validate_market(six,now=finished)
    projection=reconcile_projection(six,market_rows)
    overlap=compare_batch(market_rows,schedules,finished=finished,requests=requests,failures=failures)
    overlap["same_collector_projection_accounting"]=projection
    overlap["complete_market_projection_count"]=len(market_rows)
    overlap["projection_counts_not_authenticated_fixtures"]=True
    sample_counts=Counter(r["league"] for r in schedules)
    if (sum(v not in ("NOT_ATTEMPTED","NOT_ATTEMPTED_NO_MARKET_PROJECTION") for v in details.values())!=requests
            or any(sample_counts[l]!=int(details[l]=="SAMPLED") for l in LEAGUES)):
        raise ValueError("SCHEDULE_LEAGUE_ACCOUNTING")
    overlap["schedule_collection_by_league"]={l:{"state":details[l],"sample_count":sample_counts[l],
        "maximum_free_samples":1,"coverage_complete":False} for l in LEAGUES}
    overlap["schedule_universe_complete"]=False
    # Unknown or failed request denominators stay null rather than zero.
    for l,item in overlap["schedule_collection_by_league"].items():
        d=row_diagnostics.get(l)
        if d is not None:
            if (d["returned_rows"]!=d["inspected_rows"]+d["not_inspected_free_limit"]
                    or sum(d["disposition"].values())!=d["inspected_rows"]
                    or d["disposition"].get("ACCEPTED_LOCAL",0)!=item["sample_count"]):
                raise ValueError("SCHEDULE_ROW_ACCOUNTING")
        item["row_diagnostic"]=d
    overlap["schedule_row_denominators_complete"]=False
    from live_core_german_schedule_corroboration import review,confirm_naive
    overlap["german_schedule_research"]=review(market_rows,schedules,german_rows,finished=finished)
    confirmed,tz_report=confirm_naive(naive,german_rows,finished=finished)
    overlap["timezone_candidate_reason"]=candidate_diag.get("reason","NOT_AVAILABLE" if german_requested else "NOT_REQUESTED")
    overlap["timezone_candidate_review"]=tz_report
    # A hypothetical UTC interpretation must never enter the strict schedule
    # population. Keep the candidate-only counts separate and non-additive.
    overlap["german_timezone_candidate_market_research"]=review(market_rows,confirmed,german_rows,finished=finished)
    overlap["timezone_candidate_research_not_additive"]=True
    overlap["german_schedule_capture"]=german_capture
    overlap["openliga_requests_attempted"]=int(german_capture is not None)
    overlap["public_schedule_total_request_budget"]=7
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
    from live_germany import read_json
    results=run(settled=load(a.settled),openliga_getter=read_json)
    for name,obj in zip(("six-free.json","fixture-overlap.json","seven-gates.json"),results):
        with Path(name).open("x",encoding="utf-8") as f:json.dump(obj,f,sort_keys=True,allow_nan=False)
    print(json.dumps({"status":"HOLD","schedule_requests":results[1]["schedule_requests_attempted"],
                      "schedule_agreements":results[1]["at_least_one_other_publisher_agreement"],
                      "production_recommendations":"DISABLED"}))
if __name__=="__main__":main()
