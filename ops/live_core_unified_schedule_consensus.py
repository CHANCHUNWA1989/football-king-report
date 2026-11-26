"""Projected market/schedule cross-source conflict accounting, not authentication.

The strict SportsDB projection is used once; normalized naive candidates are
reported elsewhere and cannot count as another publisher. Rejected raw rows
are not visible here. No prices, raw IDs or team names are emitted.
"""
from collections import Counter,defaultdict
from datetime import timedelta
from live_core_same_batch_collection import LEAGUES,MAX_BATCH_AGE,stamp,validate_projection

SOURCES=("thesportsdb","openligadb","football_data_org")
STATES=("MARKET_TIME_REJECTED","MARKET_AMBIGUOUS","SOURCE_CONFLICT_OR_AMBIGUITY",
        "STALE_SOURCE_MATCH","THREE_SCHEDULE_LABELS_AGREE","TWO_SCHEDULE_LABELS_AGREE",
        "ONE_SCHEDULE_LABEL_AGREES","NO_SCHEDULE_AGREEMENT")

def key(r):return (r["league"],r["home_id"],r["away_id"])

def review(markets,sports,openliga,fd,*,finished):
    if finished.tzinfo is None or finished.utcoffset() is None:raise ValueError("NAIVE_CLOCK")
    validate_projection(markets,960,market=True)
    for rows,limit in ((sports,6),(openliga,30),(fd,960)):
        validate_projection(rows,limit)
    if any(r["league"]!="bundesliga" for r in openliga):raise ValueError("OPENLIGA_SCOPE")
    def fresh(r):
        return timedelta(0)<=finished-stamp(r["received_utc"])<=MAX_BATCH_AGE and stamp(r["kickoff_utc"])>finished
    indexes={}
    for name,rows in zip(SOURCES,(sports,openliga,fd)):
        ids=Counter(r["native_id"] for r in rows)
        index=defaultdict(list)
        for r in rows:index[key(r)].append((r,ids[r["native_id"]]))
        indexes[name]=index
    def classify(r,name):
        if name=="openligadb" and r["league"]!="bundesliga":return "OUTSIDE_SCOPE"
        candidates=indexes[name].get(key(r),[])
        if not candidates:return "NO_PROJECTED_MATCH"
        if len(candidates)!=1 or candidates[0][1]!=1:return "AMBIGUOUS"
        c=candidates[0][0]
        if not fresh(c):return "STALE_OR_STARTED"
        return "AGREE" if stamp(c["kickoff_utc"])==stamp(r["kickoff_utc"]) else "CONFLICT"
    ids=Counter(r["native_id"] for r in markets)
    natural=Counter((key(r),stamp(r["kickoff_utc"])) for r in markets)
    pairs=Counter(key(r) for r in markets)
    results={k:Counter() for k in LEAGUES}
    source_states={k:{p:Counter() for p in SOURCES} for k in LEAGUES}
    checked=0
    for r in markets:
        c=results[r["league"]]
        ko,at,up=(stamp(r[x]) for x in ("kickoff_utc","received_utc","oldest_market_update_utc"))
        if not fresh(r) or not at<=finished<ko-timedelta(minutes=10) or not timedelta(0)<=at-up<=MAX_BATCH_AGE or not timedelta(0)<=finished-up<=MAX_BATCH_AGE:
            c["MARKET_TIME_REJECTED"]+=1;continue
        if ids[r["native_id"]]!=1 or natural[(key(r),ko)]!=1 or pairs[key(r)]!=1:
            c["MARKET_AMBIGUOUS"]+=1;continue
        checked+=1
        states=[]
        for name in SOURCES:
            state=classify(r,name)
            source_states[r["league"]][name][state]+=1;states.append(state)
        if "CONFLICT" in states or "AMBIGUOUS" in states:
            label="SOURCE_CONFLICT_OR_AMBIGUITY"
        elif "STALE_OR_STARTED" in states:
            label="STALE_SOURCE_MATCH"
        else:
            label={0:"NO_SCHEDULE_AGREEMENT",1:"ONE_SCHEDULE_LABEL_AGREES",2:"TWO_SCHEDULE_LABELS_AGREE",3:"THREE_SCHEDULE_LABELS_AGREE"}[states.count("AGREE")]
        c[label]+=1
    total=sum(results.values(),Counter())
    if sum(total.values())!=len(markets):raise ValueError("MARKET_PARTITION")
    for k in LEAGUES:
        eligible=sum(results[k].values())-results[k]["MARKET_TIME_REJECTED"]-results[k]["MARKET_AMBIGUOUS"]
        if any(sum(source_states[k][p].values())!=eligible for p in SOURCES):raise ValueError("SOURCE_PARTITION")
    return {"market_rows":len(markets),"rows_checked_against_sources":checked,
            "disposition":{k:total[k] for k in STATES},
            "by_league":{k:{v:results[k][v] for v in STATES} for k in LEAGUES},
            "source_disposition_by_league":{k:{p:dict(v) for p,v in source_states[k].items()} for k in LEAGUES},
            "strict_projection_only":True,"rejected_raw_rows_not_reviewed":True,
            "naive_timezone_candidates_not_counted_as_extra_source":True,
            "source_independence_verified":False,"canonical_identity_authenticated":False,
            "authenticated_forward_samples":0,"positive_ev_verified":False,
            "production_recommendations":"DISABLED","status":"HOLD"}
