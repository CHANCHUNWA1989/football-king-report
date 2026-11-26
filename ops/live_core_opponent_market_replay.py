"""Fixed blend50 market-grade validation; historical score distributions only."""
import json
import math
from collections import defaultdict
from datetime import date
from urllib.request import Request,build_opener
from live_core_multi_source import blob,checked,row,unique,NoRedirect,LIMIT
from research_strict_json import unique_object,reject_constant
from live_core_venue_bias_replay import fetch as fetch_prior
from live_core_opponent_strength import fetch as fetch_2024,forecasts,SPECS as PRIOR_SPECS
from live_core_multi_league_stress import paired_ci
from score_distribution_vnext import GRADE_NAMES,grade_score,market_distribution

SPECS={
 "EPL":("en.1","English Premier League 2025/26",380,353,"41e223ee5954e6b634beb4bc70d7188b3183c665"),
 "BL":("de.1","Deutsche Bundesliga 2025/26",306,294,"320994ff4b376c0aa7abe7929f9b9740cfc0eff5"),
 "ES":("es.1","Spain Primera División 2025/26",380,365,"ca95ceb8861f8f1ae876eb066e71148ff773425b")}
MARKETS=(("home_minus_025","asian_handicap","HOME",-.25),
         ("home_minus_075","asian_handicap","HOME",-.75),
         ("home_plus_025","asian_handicap","HOME",.25),
         ("over_225","totals","OVER",2.25),
         ("under_275","totals","UNDER",2.75),
         ("over_300","totals","OVER",3.0))
MODELS=("baseline","blend_50")
def parse(raw,league):
    _,name,scheduled,finished,pin=SPECS[league]
    if blob(raw)!=pin:raise ValueError("BLOB_PIN_CHANGED")
    d=json.loads(checked(raw),object_pairs_hook=unique_object,parse_constant=reject_constant)
    if d["name"]!=name or len(d["matches"])!=scheduled:raise ValueError("LEAGUE_SCOPE")
    keys=set();rows=[]
    for m in d["matches"]:
        day=m["date"];h=m["team1"];a=m["team2"]
        if not "2025-07-01"<=date.fromisoformat(day).isoformat()<"2026-07-01":raise ValueError("DATE_SCOPE")
        if any(type(t) is not str or not t.strip() for t in (h,a)) or h.strip()==a.strip():raise ValueError("TEAM")
        key=(day,h.strip(),a.strip())
        if key in keys:raise ValueError("DUPLICATE_MATCH")
        keys.add(key)
        payload=m.get("score")
        # Pinned source contains bare [0,0] for records without score.ft.
        # Never interpret that untyped array as a confirmed goalless draw.
        if type(payload) is list and payload==[0,0] and all(type(v) is int for v in payload):
            continue
        if type(payload) is not dict or payload.get("ft") is None:
            raise ValueError("UNRECOGNIZED_SCORE_FORMAT")
        rows.append(row(day,h,a,payload["ft"]))
    if len(rows)!=finished:raise ValueError("FINISHED_SCOPE")
    return unique(rows)
def fetch(league):
    path=SPECS[league][0]
    url=f"https://raw.githubusercontent.com/openfootball/football.json/master/2025-26/{path}.json"
    with build_opener(NoRedirect()).open(Request(url,headers={"User-Agent":"FootballKingResearch/1.0","Accept":"application/json"}),timeout=15) as res:
        if res.geturl()!=url or res.status!=200:raise ValueError("HTTP_SOURCE")
        raw=res.read(LIMIT+1)
    return parse(raw,league)

def grade_brier(grid,x,y,market,side,line):
    probs=market_distribution(grid,market=market,side=side,line=line)["outcome_probabilities"]
    actual=grade_score(x,y,market=market,side=side,line=line)
    return math.fsum((probs[k]-(k==actual))**2 for k in GRADE_NAMES)

def report(train,test):
    rows=forecasts(train,test,include_matrices=True)
    values={name:defaultdict(list) for name in MODELS}
    for day,_,_,x,y,_,preds,grids in rows:
        k=0 if x>y else 1 if x==y else 2
        for name in MODELS:
            p,u=preds[name]
            metrics={"1x2_log_loss":-math.log(max(p[k],1e-15)),
                     "1x2_brier":math.fsum((v-(i==k))**2 for i,v in enumerate(p)),
                     "under25_brier":(u-(x+y<=2))**2}
            for label,market,side,line in MARKETS:
                metrics[label+"_grade_brier"]=grade_brier(grids[name],x,y,market,side,line)
            for metric,v in metrics.items():values[name][metric].append(v)
    result={}
    for metric,b in values["baseline"].items():
        c=values["blend_50"][metric]
        n=len(b);weeks=defaultdict(list)
        for r,x,y in zip(rows,b,c):
            weeks[date.fromisoformat(r[0]).isocalendar()[:2]].append(x-y)
        result[metric]={"baseline":math.fsum(b)/n,"blend_50":math.fsum(c)/n,
                        "baseline_minus_candidate":math.fsum(x-y for x,y in zip(b,c))/n,
                        "descriptive_ci95":paired_ci([(math.fsum(v),len(v)) for _,v in sorted(weeks.items())])}
    return {"train_n":len(train),"assessment_n":len(rows),"metrics":result}
def run():
    leagues={}
    for league,(_,_,scheduled,finished,_) in SPECS.items():
        prior=fetch_prior(league,"2023-24")
        middle=fetch_2024(league)
        latest=fetch(league)
        leagues[league]={"previously_reviewed_2024_25":{**report(prior,middle),
                           "assessment_missing":PRIOR_SPECS[league][2]-len(middle)},
                         "retrospective_2025_26":{**report(middle,latest),
                           "warmup_missing":PRIOR_SPECS[league][2]-len(middle),
                           "assessment_scheduled":scheduled,"assessment_missing":scheduled-finished}}
    return {"leagues":leagues,"fixed_candidate":"blend_50","weight_locked":.5,
            "selected_for_research_after_prior_results":True,"historical_only":True,
            "missing_scores_not_imputed":True,"incomplete_history_can_bias_results":True,
            "all_markets_same_score_matrix":True,"grade_brier_not_roi":True,
            "intervals_not_multiple_comparison_adjusted":True,"actual_market_quotes_verified":False,
            "independent_prospective_validation":False,"verified_forward_sample_credit":0,
            "model_calibrated":False,"positive_ev_verified":False,
            "production_recommendations":"DISABLED","status":"HOLD"}
if __name__=="__main__":
    print(json.dumps(run(),sort_keys=True,allow_nan=False))
