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
from live_core_market_family_inference import family_intervals, FAMILY_SIZE, UNIQUE_METRICS

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
    weekly_by_metric={}
    for metric,b in values["baseline"].items():
        c=values["blend_50"][metric]
        n=len(b);weeks=defaultdict(list)
        for r,x,y in zip(rows,b,c):
            weeks[date.fromisoformat(r[0]).isocalendar()[:2]].append(x-y)
        weekly_by_metric[metric]={k:(math.fsum(v),len(v)) for k,v in weeks.items()}
        result[metric]={"baseline":math.fsum(b)/n,"blend_50":math.fsum(c)/n,
                        "baseline_minus_candidate":math.fsum(x-y for x,y in zip(b,c))/n,
                        "descriptive_ci95":paired_ci([(math.fsum(v),len(v)) for _,v in sorted(weeks.items())])}
    family=family_intervals(weekly_by_metric)
    return {"train_n":len(train),"assessment_n":len(rows),"metrics":result,
            "family_inference":family}
# Grade labels differ, but these partitions of integer score outcomes are
# identical up to a permutation. Their multiclass Brier scores are redundant.
# Log loss and Brier also use the same match outcomes, not independent trials.
EQUIVALENT_BRIER={
    "1x2_brier":("home_minus_025_grade_brier","home_plus_025_grade_brier"),
    "over_300_grade_brier":("under_275_grade_brier",),
}
STABILITY_METRICS=("1x2_log_loss","1x2_brier","under25_brier",
                   "home_minus_075_grade_brier","over_225_grade_brier",
                   "over_300_grade_brier")
SEASON_KEYS=("previously_reviewed_2024_25","retrospective_2025_26")

def _metric(item):
    if not isinstance(item,dict):
        raise ValueError("INVALID_METRIC")
    b,c,d=(item.get(k) for k in ("baseline","blend_50","baseline_minus_candidate"))
    if not all(type(v) in (int,float) and math.isfinite(v) for v in (b,c,d)):
        raise ValueError("NONFINITE_METRIC")
    if b<0 or c<0 or abs((b-c)-d)>1e-9:
        raise ValueError("METRIC_ACCOUNTING")
    ci=item.get("descriptive_ci95")
    if ci is not None and (not isinstance(ci,(list,tuple)) or len(ci)!=2
            or not all(type(v) in (int,float) and math.isfinite(v) for v in ci)
            or ci[0]>ci[1]):
        raise ValueError("INVALID_INTERVAL")
    return {"difference":d,"ci95":list(ci) if ci is not None else None}

def stability(leagues):
    """Descriptive two-season robustness, not a promotion gate or pooled CI."""
    if not isinstance(leagues,dict) or set(leagues)!=set(SPECS):
        raise ValueError("LEAGUE_SCOPE")
    out={}
    n_total=missing_total=0
    for league,periods in sorted(leagues.items()):
        seasons={}
        for season in SEASON_KEYS:
            block=periods[season]
            n,missing=block["assessment_n"],block["assessment_missing"]
            if (type(n) is not int or type(missing) is not int
                    or n<=0 or missing<0 or n+missing>1000
                    or ("assessment_scheduled" in block and
                        (type(block["assessment_scheduled"]) is not int
                         or block["assessment_scheduled"]!=n+missing))):
                raise ValueError("ASSESSMENT_ACCOUNTING")
            expected=PRIOR_SPECS[league][2] if season==SEASON_KEYS[0] else SPECS[league][2]
            if n+missing!=expected:
                raise ValueError("ASSESSMENT_SCOPE")
            n_total+=n;missing_total+=missing
            metrics=block["metrics"]
            parsed={key:_metric(metrics[key]) for key in STABILITY_METRICS}
            for base,aliases in EQUIVALENT_BRIER.items():
                for alias in aliases:
                    alt=_metric(metrics[alias])
                    for k in ("baseline","blend_50","baseline_minus_candidate"):
                        if abs(metrics[base][k]-metrics[alias][k])>1e-9:
                            raise ValueError("EQUIVALENT_GRADE_CONFLICT")
                    x,y=parsed[base]["ci95"],alt["ci95"]
                    if ((x is None)!=(y is None) or
                        (x is not None and any(abs(a-b)>1e-9 for a,b in zip(x,y)))):
                        raise ValueError("EQUIVALENT_INTERVAL_CONFLICT")
            seasons[season]={"assessment_n":n,"assessment_missing":missing,
                             "assessment_coverage":n/(n+missing),"metrics":parsed}
        summary={}
        for key in STABILITY_METRICS:
            first,second=(seasons[s]["metrics"][key] for s in SEASON_KEYS)
            ds=[first["difference"],second["difference"]]
            intervals=[first["ci95"],second["ci95"]]
            if any(d<0 for d in ds):
                state="DEGRADATION_IN_AT_LEAST_ONE_SEASON"
            elif any(d==0 for d in ds):
                state="NO_STRICT_TWO_SEASON_IMPROVEMENT"
            elif all(ci is not None and ci[0]>0 for ci in intervals):
                state="POSITIVE_DESCRIPTIVE_INTERVALS_BOTH_SEASONS"
            else:
                state="DIRECTIONALLY_POSITIVE_UNCERTAIN"
            summary[key]={"state":state,"season_differences":ds,
                          "season_intervals":intervals,
                          "latest_season_interval_excludes_zero_positive":
                              intervals[1] is not None and intervals[1][0]>0}
        out[league]={"seasons":seasons,"metric_stability":summary}
    return {"leagues":out,"total_scored_observations":n_total,
            "total_missing_observations":missing_total,
            "equivalent_brier_aliases":EQUIVALENT_BRIER,
            "distinct_scoring_rules":list(STABILITY_METRICS),
            "independent_evidence_count":None,"pooled_confidence_interval":None,
            "multiple_comparisons_adjusted":False,"missingness_bias_ruled_out":False,
            "candidate_locked_after_prior_results":True,"automatic_promotion":False,
            "verified_forward_sample_credit":0,"positive_ev_verified":False,
            "production_recommendations":"DISABLED","status":"HOLD"}

def family_summary(leagues):
    """Reconcile the 36 planned retrospective comparisons; never promote."""
    evaluated=unavailable=0
    positive=[];negative=[]
    for league,periods in sorted(leagues.items()):
        for season in SEASON_KEYS:
            block=periods[season];f=block["family_inference"]
            if (f["family_size"]!=FAMILY_SIZE or type(f["n"]) is not int
                    or f["n"]!=block["assessment_n"]
                    or set(f["intervals"])!=set(UNIQUE_METRICS)
                    or f["production_recommendations"]!="DISABLED"
                    or type(f["qualification_credit"]) is not int or f["qualification_credit"]!=0):
                raise ValueError("FAMILY_ACCOUNTING")
            positives=[];negatives=[]
            for metric in UNIQUE_METRICS:
                interval=f["intervals"][metric]
                if interval is None:
                    unavailable+=1
                    if f["descriptive_coverage_eligible"] is not False:
                        raise ValueError("FAMILY_ELIGIBILITY")
                    continue
                if (f["descriptive_coverage_eligible"] is not True
                        or not isinstance(interval,list) or len(interval)!=2
                        or not all(type(v) in (int,float) and math.isfinite(v) for v in interval)
                        or interval[0]>interval[1]):
                    raise ValueError("FAMILY_INTERVAL")
                evaluated+=1
                record={"league":league,"season":season,"metric":metric,
                        "interval":interval}
                if interval[0]>0:
                    positives.append(metric);positive.append(record)
                if interval[1]<0:
                    negatives.append(metric);negative.append(record)
            if (f["positive_lower_bound_metrics"]!=positives
                    or f["negative_upper_bound_metrics"]!=negatives):
                raise ValueError("FAMILY_SIGN_ACCOUNTING")
    if evaluated+unavailable!=FAMILY_SIZE:
        raise ValueError("FAMILY_SCOPE")
    return {"planned_comparisons":FAMILY_SIZE,"evaluated_comparisons":evaluated,
            "unavailable_comparisons":unavailable,
            "positive_adjusted_intervals":positive,"negative_adjusted_intervals":negative,
            "latest_season_positive_count":sum(r["season"]==SEASON_KEYS[1] for r in positive),
            "historical_only":True,"independent_prospective_validation":False,
            "automatic_promotion":False,"qualification_credit":0,
            "positive_ev_verified":False,"production_recommendations":"DISABLED","status":"HOLD"}

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
    return {"leagues":leagues,"cross_season_stability":stability(leagues),
            "family_summary":family_summary(leagues),
            "fixed_candidate":"blend_50","weight_locked":.5,
            "selected_for_research_after_prior_results":True,"historical_only":True,
            "missing_scores_not_imputed":True,"incomplete_history_can_bias_results":True,
            "all_markets_same_score_matrix":True,"grade_brier_not_roi":True,
            "original_descriptive_ci95_not_adjusted":True,
            "additional_family_interval_method":"BONFERRONI_PERCENTILE_WEEK_BLOCK_BOOTSTRAP",
            "family_size":FAMILY_SIZE,"unique_metrics_per_cohort":list(UNIQUE_METRICS),
            "actual_market_quotes_verified":False,
            "independent_prospective_validation":False,"verified_forward_sample_credit":0,
            "model_calibrated":False,"positive_ev_verified":False,
            "production_recommendations":"DISABLED","status":"HOLD"}
if __name__=="__main__":
    print(json.dumps(run(),sort_keys=True,allow_nan=False))
