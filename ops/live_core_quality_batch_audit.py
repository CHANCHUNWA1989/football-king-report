"""Read-only reconciliation of the same-run market quality summaries.
Counts are aggregate marginals, not authenticated event-level joins."""
import json
import subprocess
from datetime import timedelta
from live_core_blend50_source_bridge import decode
from live_core_blend50_forward_seal import instant

PINS={"market":"dad0a4469caf2c2d1e8b4e5c5a53050b97cb8985",
      "overlap":"97de2adf2574a05075d7d32dc2af451ad59bde68",
      "gates":"5e847ede9e9d906b4ed77de20f744535f4ef64ba"}
LEAGUES=("epl","championship","bundesliga","laliga","seriea","ligue1")
MARKETS=("utc_identity_events","full_1x2_events","paired_spread_events","paired_totals_events")
def count(v):
    if type(v) is not int or v<0:raise ValueError("INVALID_COUNT")
    return v
def index(rows):
    if type(rows) is not list or len(rows)!=6:raise ValueError("LEAGUE_SCOPE")
    out={}
    for r in rows:
        k=r["league"]
        if k not in LEAGUES or k in out:raise ValueError("LEAGUE_SCOPE")
        out[k]=r
    return out
def reconcile(m,o,g):
    for d,schema in zip((m,o,g),("football-king-six-free-league-quality-v1","football-king-six-league-two-publisher-fixtures-v1","football-king-seven-evidence-gates-v1")):
        if d["schema"]!=schema or d["production_recommendations"]!="DISABLED":raise ValueError("UNSAFE_SCHEMA")
    stamps=[instant(x["captured_utc"]) for x in (m,o,g)]
    if len(set(stamps))!=1:raise ValueError("BATCH_CLOCK_MISMATCH")
    if m["raw_bookmaker_quotes_published"] is not False or o["original_bookmaker_quotes_stored"] is not False or g["can_promote_model"] is not False or g["can_recommend_bets"] is not False:raise ValueError("UNSAFE_FLAGS")
    if count(m["requests_attempted"])>count(m["max_requests"]):raise ValueError("QUOTA")
    mi,oi=index(m["coverage"]),index(o["by_league"])
    total={k:0 for k in MARKETS};eligible=0;lower=upper=0;valid=one=two=0;detail={}
    for league in LEAGUES:
        r=mi[league];q=oi[league];n=count(r["upcoming_events"])
        vals=[count(r[k]) for k in MARKETS]
        if any(v>n for v in vals) or r["not_executable_odds"] is not True:raise ValueError("MARKET_COUNT_OR_FLAG")
        for k,v in zip(MARKETS,vals):total[k]+=v
        lo=max(0,sum(vals)-3*n);hi=min(vals)
        lower+=lo;upper+=hi;eligible+=int(lo>0)
        a,b,c,d=[count(q[k]) for k in ("market_events","time_valid_market_events","one_other_publisher_agreements","two_other_publisher_agreements")]
        if not 0<=d<=c<=b<=a:raise ValueError("OVERLAP_ORDER")
        valid+=b;one+=c;two+=d
        detail[league]={"market_observations":n,"all_four_market_fields_intersection_bounds":[lo,hi],
                        "separate_overlap_time_valid":b,"separate_overlap_two_publishers":d}
    if (valid,one,two)!=(count(o["time_valid_market_count"]),count(o["at_least_one_other_publisher_agreement"]),count(o["at_least_two_other_publisher_agreements"])):raise ValueError("OVERLAP_TOTAL")
    if sum(count(r["market_events"]) for r in oi.values())!=count(o["market_sample_count"]):raise ValueError("OVERLAP_DENOMINATOR")
    checks=g["checks"]
    if len(checks)!=7 or len({r["key"] for r in checks})!=7 or any(r["state"] not in ("PASS","PARTIAL","HOLD") for r in checks):raise ValueError("GATE_SCOPE")
    states={s:sum(r["state"]==s for r in checks) for s in ("PASS","PARTIAL","HOLD")}
    if (states["PASS"],states["PARTIAL"],states["HOLD"],len(checks))!=(count(g["passed"]),count(g["partial"]),count(g["held"]),count(g["total"])):raise ValueError("GATE_TOTAL")
    market_asof=instant(o["market_as_of_utc"]) if o["market_as_of_utc"] else None
    secondary=instant(o["secondary_as_of_utc"]) if o["secondary_as_of_utc"] else None
    if any(t>stamps[0] for t in (market_asof,secondary) if t is not None):raise ValueError("FUTURE_CLOCK")
    # Separate freshness of the overlap snapshot from the current aggregate
    # collector envelope. Ten hours is a diagnostic ceiling, not quote validity.
    clocks={}
    blockers=[]
    for name,t in (("market",market_asof),("secondary",secondary)):
        declared=o.get(name+"_fresh")
        if declared is not None and type(declared) is not bool:
            raise ValueError("INVALID_FRESHNESS_FLAG")
        age=(stamps[0]-t).total_seconds()/3600 if t is not None else None
        state=("CLOCK_MISSING" if age is None else
               "OLDER_THAN_DIAGNOSTIC_CEILING" if age>10 else "WITHIN_DIAGNOSTIC_CEILING")
        clocks[name]={"as_of_utc":t.isoformat() if t else None,"age_hours":age,
                      "diagnostic_state":state,"source_declared_fresh":declared}
        if state!="WITHIN_DIAGNOSTIC_CEILING" or declared is not True:
            blockers.append(name.upper()+"_FRESHNESS_NOT_ESTABLISHED")
    if any(v["source_declared_fresh"] is True and v["diagnostic_state"]!="WITHIN_DIAGNOSTIC_CEILING"
           for v in clocks.values()):
        blockers.append("DECLARED_FRESHNESS_CONTRADICTS_DIAGNOSTIC_CLOCK")
    if one==0:blockers.append("NO_RECORDED_OTHER_PUBLISHER_AGREEMENTS")
    if o.get("secondary_licensed_source_validation") is not True:
        blockers.append("SECONDARY_SOURCE_AUTHORIZATION_UNVERIFIED")
    blockers.extend(("EVENT_LEVEL_MARKET_JOIN_UNVERIFIED","EXECUTABLE_QUOTE_UNAVAILABLE"))
    observed=sum(v["market_observations"] for v in detail.values())
    readiness={"aggregate_market_observations":observed,
               "separate_overlap_market_observations":count(o["market_sample_count"]),
               "observed_population_difference":observed-count(o["market_sample_count"]),
               "population_difference_is_not_missing_fixture_count":True,
               "diagnostic_ceiling_hours":10,"overlap_source_clocks":clocks,
               "blockers":blockers,"joined_eligible_fixtures":None,
               "executable_verified_fixtures":0,"authenticated_forward_samples":0,
               "production_recommendations":"DISABLED","status":"HOLD"}
    return {"captured_utc":stamps[0].isoformat(),"market_field_counts":total,
            "source_readiness_diagnostic":readiness,
            "market_intersection_bounds":[lower,upper],"leagues_with_nonzero_lower_bound":eligible,
            "separate_overlap_valid":valid,"separate_overlap_one_publisher":one,"separate_overlap_two_publishers":two,
            "overlap_market_age_hours":(stamps[0]-market_asof).total_seconds()/3600 if market_asof else None,
            "overlap_secondary_clock_available":secondary is not None,
            "gate_states":states,"by_league":detail,
            "same_batch_envelope_not_same_event_population":True,"cross_source_event_join_verified":False,
            "market_executable":False,"seal_inputs_emitted":0,"authenticated_forward_samples":0,
            "positive_ev_verified":False,"production_recommendations":"DISABLED","status":"HOLD"}
def replay():
    docs=[decode(subprocess.check_output(["git","cat-file","blob",PINS[k]],timeout=10),PINS[k]) for k in ("market","overlap","gates")]
    return {"pinned_quality_batch":True,"source_blobs":PINS,**reconcile(*docs)}
if __name__=="__main__":
    print(json.dumps(replay(),sort_keys=True,allow_nan=False))
