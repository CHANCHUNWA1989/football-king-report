"""German market/schedule corroboration: separate source identities, no admission."""
import json
from collections import Counter,defaultdict
from datetime import timedelta
from live_core_same_batch_collection import validate_projection,stamp,MAX_BATCH_AGE,clock,schedule_diagnostic,naive_utc_candidate
from live_core_openliga_schedule_smoke import capture
from secondary_sources import fetch,SD_BD
from live_germany import read_json

def review(markets,sportsdb,openliga,*,finished):
    validate_projection(markets,960,market=True)
    validate_projection(sportsdb,6)
    validate_projection(openliga,30)
    if any(r["league"]!="bundesliga" for r in openliga):raise ValueError("OPENLIGA_SCOPE")
    if finished.tzinfo is None:raise ValueError("NAIVE_CLOCK")
    def key(r):return (r["league"],r["home_id"],r["away_id"])
    def fresh(r):return timedelta(0)<=finished-stamp(r["received_utc"])<=MAX_BATCH_AGE
    def index(rows):
        ids=Counter(r["native_id"] for r in rows);groups=defaultdict(list)
        for r in rows:
            if r["league"]=="bundesliga":groups[key(r)].append((r,ids[r["native_id"]]))
        return groups
    sources=[index(sportsdb),index(openliga)]
    def state(r,idx):
        candidates=idx.get(key(r),[])
        if not candidates:return "MISSING"
        if len(candidates)!=1 or candidates[0][1]!=1:return "AMBIGUOUS"
        c=candidates[0][0]
        if not fresh(c):return "STALE"
        return "AGREE" if stamp(c["kickoff_utc"])==stamp(r["kickoff_utc"]) else "CONFLICT"
    ids=Counter(r["native_id"] for r in markets);natural=Counter((key(r),stamp(r["kickoff_utc"])) for r in markets)
    pair_counts=Counter(key(r) for r in markets)
    counts=Counter();per_source={"thesportsdb":Counter(),"openligadb":Counter()}
    german=[r for r in markets if r["league"]=="bundesliga"]
    for r in german:
        ko,at,up=(stamp(r[k]) for k in ("kickoff_utc","received_utc","oldest_market_update_utc"))
        if (not fresh(r) or not at<=finished<ko-timedelta(minutes=10)
                or not timedelta(0)<=at-up<=MAX_BATCH_AGE or not timedelta(0)<=finished-up<=MAX_BATCH_AGE):
            counts["MARKET_TIME_REJECTED"]+=1;continue
        if ids[r["native_id"]]!=1 or natural[(key(r),ko)]!=1 or pair_counts[key(r)]!=1:
            counts["MARKET_ID_AMBIGUOUS"]+=1;continue
        s,o=(state(r,idx) for idx in sources)
        per_source["thesportsdb"][s]+=1;per_source["openligadb"][o]+=1
        # Neither a conflict nor an ambiguous alternative may be ignored.
        if "CONFLICT" in (s,o) or "AMBIGUOUS" in (s,o):label="SOURCE_CONFLICT_OR_AMBIGUITY"
        elif s==o=="AGREE":label="BOTH_AGREE_UNAUTHENTICATED"
        elif s=="AGREE":label="SPORTSDB_ONLY_AGREES"
        elif o=="AGREE":label="OPENLIGA_ONLY_AGREES"
        else:label="NO_FRESH_AGREEMENT"
        counts[label]+=1
    if sum(counts.values())!=len(german):raise ValueError("GERMAN_DENOMINATOR")
    evaluated=len(german)-counts["MARKET_TIME_REJECTED"]-counts["MARKET_ID_AMBIGUOUS"]
    if any(sum(v.values())!=evaluated for v in per_source.values()):
        raise ValueError("GERMAN_SOURCE_DENOMINATOR")

    return {"german_market_rows":len(german),"market_disposition":dict(counts),
            "source_disposition":{k:dict(v) for k,v in per_source.items()},
            "sportsdb_german_rows":sum(r["league"]=="bundesliga" for r in sportsdb),
            "openliga_german_rows":len(openliga),"no_source_id_namespace_collapse":True,
            "source_independence_verified":False,"canonical_identity_authenticated":False,
            "authenticated_forward_samples":0,"production_recommendations":"DISABLED","status":"HOLD"}

def confirm_naive(candidates,openliga,*,finished):
    validate_projection(candidates,1);validate_projection(openliga,30)
    if finished.tzinfo is None or any(r["league"]!="bundesliga" for r in candidates+openliga):
        raise ValueError("TIMEZONE_SCOPE")
    reasons=Counter();out=[]
    ids=Counter(r["native_id"] for r in openliga)
    def fresh(r):
        return timedelta(0)<=finished-stamp(r["received_utc"])<=MAX_BATCH_AGE and stamp(r["kickoff_utc"])>finished
    for r in candidates:
        if not fresh(r):reasons["STALE_OR_STARTED"]+=1;continue
        matched=[x for x in openliga if (x["home_id"],x["away_id"])==(r["home_id"],r["away_id"])]
        if not matched:reasons["NO_OPENLIGA_TEAM_MATCH"]+=1;continue
        if len(matched)!=1 or ids[matched[0]["native_id"]]!=1:reasons["AMBIGUOUS_OPENLIGA"]+=1;continue
        c=matched[0]
        if not fresh(c):reasons["OPENLIGA_STALE_OR_STARTED"]+=1;continue
        if stamp(c["kickoff_utc"])!=stamp(r["kickoff_utc"]):reasons["KICKOFF_CONFLICT"]+=1;continue
        out.append(r);reasons["EXACT_LOCAL_AGREEMENT"]+=1
    if sum(reasons.values())!=len(candidates):raise ValueError("TIMEZONE_DENOMINATOR")
    return out,{"candidate_count":len(candidates),"locally_corroborated":len(out),"disposition":dict(reasons),
                "utc_interpretation_is_research_only":True,"native_timestamp_attested":False,
                "authenticated_forward_samples":0,"production_recommendations":"DISABLED"}

def schedule_only(*,fetcher=fetch,getter=read_json,now=clock):
    # One public request per provider; no market API, no retry.
    body,state=fetcher("thesportsdb",f"https://www.thesportsdb.com/api/v1/json/123/eventsnextleague.php?id={SD_BD['bundesliga']}",{})
    sports=[];diag=None;naive=[];naive_reason="NOT_AVAILABLE"
    if state=="OK":
        try:
            received=now()
            sports,diag=schedule_diagnostic(body,"bundesliga",received)
            naive,naive_reason=naive_utc_candidate(body,received)
        except (ValueError,TypeError,OverflowError):state="INVALID_DATA"
    if state not in ("OK","RATE_LIMITED","KEY_REJECTED","PLAN_OR_LEAGUE_RESTRICTED","HTTP_ERROR","NETWORK_ERROR","INVALID_DATA"):state="OTHER_ERROR"
    ol,report=capture(getter=getter,now=now);finished=now()
    confirmed,tz_report=confirm_naive(naive,ol,finished=finished)
    matches=0;conflicts=0
    for s in sports:
        if not timedelta(0)<=finished-stamp(s["received_utc"])<=MAX_BATCH_AGE:continue
        c=[r for r in ol if (r["home_id"],r["away_id"])==(s["home_id"],s["away_id"])]
        if len(c)==1 and timedelta(0)<=finished-stamp(c[0]["received_utc"])<=MAX_BATCH_AGE:
            if stamp(c[0]["kickoff_utc"])==stamp(s["kickoff_utc"]):matches+=1
            else:conflicts+=1
    return {"public_schedule_pair_probe":True,"checked_utc":finished.isoformat(),
            "requests_attempted":2,"sportsdb_response":state,"sportsdb_diagnostic":diag,
            "sportsdb_local_rows":len(sports),"openliga_capture":report,
            "timezone_candidate_reason":naive_reason,"timezone_candidate_review":tz_report,
            "local_exact_schedule_agreements":matches,"local_kickoff_conflicts":conflicts,
            "market_collection_attempted":False,"independent_identity_verified":False,
            "authenticated_forward_samples":0,"production_recommendations":"DISABLED","status":"HOLD"}
if __name__=="__main__":print(json.dumps(schedule_only(),sort_keys=True,allow_nan=False))
