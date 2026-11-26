"""Frozen 2025/26 holdout, partial public results only; no reselection."""
import json
from urllib.request import Request,build_opener
from live_core_multi_source import blob,checked,row,unique,NoRedirect,LIMIT
from vnext_direct_transport_offline import unique_object,reject_constant
from live_core_unified_score_fusion import observations,assess

COHORTS={
 "EPL":("en.1","English Premier League 2025/26","41e223ee5954e6b634beb4bc70d7188b3183c665",380,353,"team"),
 "BL":("de.1","Deutsche Bundesliga 2025/26","320994ff4b376c0aa7abe7929f9b9740cfc0eff5",306,294,"elo")}


def parse_cohort(raw,league):
    _,name,pin,total,finished,_=COHORTS[league]
    if blob(raw)!=pin:
        raise ValueError("PIN_CHANGED")
    d=json.loads(checked(raw),object_pairs_hook=unique_object,parse_constant=reject_constant)
    if type(d) is not dict or d.get("name")!=name or type(d.get("matches")) is not list or len(d["matches"])!=total:
        raise ValueError("COHORT_SCOPE")
    rows=[]
    all_keys=[]
    excluded=0
    for m in d["matches"]:
        if type(m) is not dict or not {"date","team1","team2","score"}<=m.keys():
            raise ValueError("MATCH_SCHEMA")
        # Validate every fixture identity, including the excluded encoding.
        key=row(m["date"],m["team1"],m["team2"],[0,0])
        all_keys.append(key)
        if not "2025-07-01"<=key[0]<"2026-07-01":
            raise ValueError("SEASON_DATE")
        score=m["score"]
        if type(score) is dict and "ft" in score:
            rows.append(row(m["date"],m["team1"],m["team2"],score["ft"]))
        elif type(score) is list and len(score)==2 and all(type(x) is int and x==0 for x in score):
            # The two frozen blobs contain exactly this alternate encoding.
            # Exclude from this prespecified FT-only cohort; do not infer
            # that it is a missing match, a placeholder, or a confirmed draw.
            excluded+=1
        else:
            raise ValueError("UNRECOGNIZED_SCORE_ENCODING")
    unique(all_keys)
    if len(rows)!=finished or excluded!=total-finished:
        raise ValueError("FINISHED_COHORT_SCOPE")
    return unique(rows)


def fetch(league):
    path=COHORTS[league][0]
    url=f"https://raw.githubusercontent.com/openfootball/football.json/master/2025-26/{path}.json"
    with build_opener(NoRedirect()).open(Request(url,headers={"User-Agent":"FootballKingResearch/1.0","Accept":"application/json"}),timeout=15) as res:
        if res.geturl()!=url or res.status!=200:
            raise ValueError("HTTP_SOURCE")
        raw=res.read(LIMIT+1)
    if len(raw)>LIMIT:
        raise ValueError("SIZE_LIMIT")
    return parse_cohort(raw,league)


def report():
    leagues={}
    for league,(_,_,_,total,finished,selected) in COHORTS.items():
        obs=observations(fetch(league))
        base=assess(obs,"league"); cand=assess(obs,selected)
        leagues[league]={"scheduled":total,"finished_available":finished,
                         "excluded_alternate_score_encoding":total-finished,"assessment_n":len(obs),
                         "excluded_rows_may_be_true_scoreless_draws":True,
                         "frozen_candidate":selected,"baseline":base,"candidate":cand,
                         "objective_improved":cand["objective"]<base["objective"],
                         "all_market_brier_not_worse":all(cand[k]<=base[k] for k in
                             ("brier","under15_brier","under25_brier","ah_grade_brier")),
                         "missingness_bias_not_ruled_out":True}
    return {"leagues":leagues,"historical_holdout":True,"independently_attested":False,
            "source_authenticated":False,"model_calibrated":False,"automatic_promotion":False,
            "verified_forward_sample_credit":0,"positive_ev_verified":False,
            "production_recommendations":"DISABLED","status":"HOLD"}


if __name__=="__main__":
    print(json.dumps(report(),sort_keys=True,allow_nan=False))
