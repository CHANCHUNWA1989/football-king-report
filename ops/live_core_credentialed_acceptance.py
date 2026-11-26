"""Read-only credentialed acceptance. Emit allowlisted counts, never prices or secrets."""
import json
import os
from collections import Counter
from live_core_same_batch_collection import run,clock,LEAGUES
from live_core_unified_schedule_consensus import STATES,SOURCES,SOURCE_STATES,joint_label
from live_core_football_data_schedule import collect as collect_fd
from live_germany import read_json
from six_league_free_upgrade import validate as validate_market
from six_league_fixture_overlap import validate as validate_overlap

def number(v,limit):
    if type(v) is not int or not 0<=v<=limit:raise ValueError("COUNT_BOUND")
    return v

def summarize(six,overlap,gates,*,market_configured,fd_configured,standalone=None,now):
    validate_market(six,now=now);validate_overlap(overlap)
    if six["captured_utc"]!=overlap["captured_utc"] or six["captured_utc"]!=gates["captured_utc"]:raise ValueError("BATCH_CLOCK")
    if any(d["production_recommendations"]!="DISABLED" for d in (six,overlap,gates)) or gates["can_promote_model"] is not False or gates["can_recommend_bets"] is not False:raise ValueError("UNSAFE_GATE")
    if six["configured"] is not market_configured:raise ValueError("CONFIG_MISMATCH")
    calls=number(six["requests_attempted"],7)
    n=number(overlap["complete_market_projection_count"],960)
    if n!=overlap["market_sample_count"]:raise ValueError("PROJECTION_COUNT")
    valid=number(overlap["time_valid_market_count"],n)
    fd=overlap["football_data_schedule_capture"]
    if fd is not None and standalone is not None:raise ValueError("DOUBLE_FD_CAPTURE")
    fd=fd if fd is not None else standalone
    fd_calls=number(fd["requests_attempted"],6) if fd is not None else 0
    if (not fd_configured and fd_calls) or (not market_configured and calls):raise ValueError("UNCONFIGURED_REQUEST")
    if fd is not None and len(fd["attempts"])!=fd_calls:raise ValueError("FD_ATTEMPT_COUNT")
    allowed={"OK","RATE_LIMITED","KEY_REJECTED","PLAN_OR_LEAGUE_RESTRICTED","HTTP_ERROR","NETWORK_ERROR","INVALID_DATA","OTHER_ERROR"}
    fd_summary={}
    if fd is not None:
        for k,r in fd["attempts"].items():
            if k not in LEAGUES or r["status"] not in allowed:raise ValueError("FD_SCOPE")
            v=number(r["rows"],160)
            if r["status"]!="OK" and v:raise ValueError("FAILED_ROWS")
            fd_summary[k]={"status":r["status"],"scheduled_rows":v}
    fd_join=number(overlap["football_data_schedule_research"]["local_agreements"],n)
    if fd_join and (not fd_configured or fd is None or standalone is not None):raise ValueError("UNRECORDED_FD_JOIN")
    if standalone is not None and (fd_calls!=1 or set(fd_summary)!={"epl"}):raise ValueError("STANDALONE_SCOPE")
    schedule_calls=number(overlap["schedule_requests_attempted"],6)+number(overlap["openliga_requests_attempted"],1)
    rows=sum(r["scheduled_rows"] for r in fd_summary.values())
    if fd_join>min(rows,n):raise ValueError("FD_JOIN_DENOMINATOR")
    if not market_configured and (n or valid or schedule_calls):raise ValueError("UNCONFIGURED_MARKET_OBSERVATION")
    consensus=overlap["unified_schedule_consensus_research"]
    if (consensus.get("production_recommendations")!="DISABLED" or consensus.get("status")!="HOLD"
            or consensus.get("canonical_identity_authenticated") is not False
            or consensus.get("source_independence_verified") is not False
            or number(consensus["authenticated_forward_samples"],0)!=0):
        raise ValueError("UNSAFE_CONSENSUS")
    if number(consensus["market_rows"],960)!=n:raise ValueError("CONSENSUS_POPULATION")
    d=consensus["disposition"]
    if not isinstance(d,dict) or set(d)!=set(STATES):raise ValueError("CONSENSUS_SCOPE")
    counts={k:number(d[k],n) for k in STATES}
    if sum(counts.values())!=n:raise ValueError("CONSENSUS_PARTITION")
    checked=number(consensus["rows_checked_against_sources"],n)
    if checked!=n-counts["MARKET_TIME_REJECTED"]-counts["MARKET_AMBIGUOUS"]:
        raise ValueError("CONSENSUS_CHECKED")
    per=consensus["by_league"]
    if not isinstance(per,dict) or set(per)!=set(LEAGUES):raise ValueError("CONSENSUS_LEAGUE_SCOPE")
    for row in per.values():
        if not isinstance(row,dict) or set(row)!=set(STATES):raise ValueError("CONSENSUS_SCOPE")
        for v in row.values():number(v,n)
    if any(sum(per[l][k] for l in LEAGUES)!=counts[k] for k in STATES):
        raise ValueError("CONSENSUS_LEAGUE_PARTITION")
    # Reconstruct the published dispositions from the joint source patterns.
    # Marginal provider counts alone cannot demonstrate simultaneous agreement.
    patterns=consensus["joint_source_patterns_by_league"]
    source=consensus["source_disposition_by_league"]
    if not isinstance(patterns,dict) or set(patterns)!=set(LEAGUES) or not isinstance(source,dict) or set(source)!=set(LEAGUES):
        raise ValueError("CONSENSUS_PATTERN_SCOPE")
    market_by_league={r["league"]:r["market_events"] for r in overlap["by_league"]}
    for l in LEAGUES:
        row=per[l]
        if sum(row.values())!=number(market_by_league[l],n):raise ValueError("CONSENSUS_LEAGUE_POPULATION")
        if not isinstance(patterns[l],dict) or len(patterns[l])>216 or not isinstance(source[l],dict) or set(source[l])!=set(SOURCES):
            raise ValueError("CONSENSUS_PATTERN_SCOPE")
        reconstructed=Counter()
        marginals={p:Counter() for p in SOURCES}
        for k,v in patterns[l].items():
            states=k.split("|") if isinstance(k,str) else []
            if (len(states)!=3 or not set(states)<=SOURCE_STATES
                    or states[0]=="OUTSIDE_SCOPE" or states[2]=="OUTSIDE_SCOPE"
                    or (states[1]=="OUTSIDE_SCOPE")!=(l!="bundesliga")):
                raise ValueError("CONSENSUS_PATTERN_STATE")
            if number(v,n)==0:raise ValueError("CONSENSUS_PATTERN_ZERO")
            reconstructed[joint_label(states)]+=v
            for p,s in zip(SOURCES,states):marginals[p][s]+=v
        if any(reconstructed[k]!=row[k] for k in STATES if k not in ("MARKET_TIME_REJECTED","MARKET_AMBIGUOUS")):
            raise ValueError("CONSENSUS_PATTERN_PARTITION")
        for p in SOURCES:
            d=source[l][p]
            if not isinstance(d,dict) or set(d)-SOURCE_STATES or any(number(v,n)==0 for v in d.values()) or d!=dict(marginals[p]):
                raise ValueError("CONSENSUS_SOURCE_PARTITION")
    market_state="NOT_CONFIGURED" if not market_configured else "NO_COMPLETE_MARKET" if not n else "NO_FRESH_MARKET" if not valid else "FRESH_MARKET_OBSERVED"
    fd_state="NOT_CONFIGURED" if not fd_configured else "NO_REQUEST" if not fd_calls else "NO_LOCAL_SCHEDULE" if not rows else "LOCAL_SCHEDULE_OBSERVED"
    return {"schema":"football-king-credentialed-acceptance-v1","checked_utc":now.isoformat(),
            "market_configured":market_configured,"football_data_configured":fd_configured,
            "market_state":market_state,"football_data_state":fd_state,
            "market_requests":calls,"public_schedule_requests":schedule_calls,"football_data_requests":fd_calls,
            "complete_market_rows":n,"fresh_market_rows":valid,"football_data_by_league":fd_summary,
            "football_data_local_market_agreements":fd_join,"standalone_epl_probe":standalone is not None,
            "local_joint_observation":fd_join>0,"unified_schedule_disposition":counts,
            "unified_schedule_checked_rows":checked,"unified_schedule_counts_not_authenticated":True,"source_independence_authenticated":False,
            "actual_market_executable_verified":False,"authenticated_forward_samples":0,
            "positive_ev_verified":False,"production_recommendations":"DISABLED","status":"HOLD"}

def accept(*,market_token="",fd_token="",runner=run,fd_collector=collect_fd,now=clock,**kwargs):
    six,o,g=runner(token=market_token,football_data_token=fd_token,now=now,**kwargs)
    standalone=None
    # If no market rows, the integrated collector cannot test FD. One isolated
    # EPL request only, no fallback retry after a provider denial.
    if fd_token and o["football_data_schedule_capture"] is None:
        _,standalone=fd_collector(["epl"],token=fd_token,now=now)
    return summarize(six,o,g,market_configured=bool(market_token),fd_configured=bool(fd_token),standalone=standalone,now=now())

if __name__=="__main__":
    r=accept(market_token=os.environ.get("PROPLINE_API_KEY",""),fd_token=os.environ.get("FOOTBALL_DATA_ORG_TOKEN",""),openliga_getter=read_json)
    print(json.dumps(r,sort_keys=True,allow_nan=False))
