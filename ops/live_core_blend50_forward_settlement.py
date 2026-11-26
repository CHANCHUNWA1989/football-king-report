"""Local replay and paired settlement of locked blend50 research.

Caller-provided observations are not authenticated. Recomputed hashes establish
local consistency only, not existence before kickoff or source independence.
"""
import argparse
import json
import math
from collections import defaultdict
from datetime import datetime,timedelta,timezone
from pathlib import Path
from live_core_blend50_forward_seal import seal,digest,instant,fields,identifier,load,PROTOCOL
from live_core_opponent_market_replay import MARKETS,grade_brier
from live_core_multi_league_stress import paired_ci
from score_distribution_vnext import score_matrix

MODELS=("baseline","blend_50")
MAX_CASES=2000
METRICS=("1x2_log_loss","1x2_brier","under25_brier")+tuple(k+"_grade_brier" for k,_,_,_ in MARKETS)

def settle(original,envelope,results,*,now=None):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError("NAIVE_NOW")
    now=now.astimezone(timezone.utc)
    fields(envelope,"record record_sha256")
    record=envelope["record"]
    if digest(record)!=envelope["record_sha256"]:raise ValueError("RECORD_DIGEST_MISMATCH")
    captured=instant(record["captured_utc"])
    # Rebuild the complete seal from original archived inputs. Do not trust
    # caller-supplied model probabilities or editable self-reported flags.
    if digest(seal(original,now=captured))!=digest(envelope):
        raise ValueError("SEALED_REPLAY_MISMATCH")
    f=record["fixture"];ko=instant(f["kickoff_utc"])
    if now<ko+timedelta(minutes=120):raise ValueError("IMMATURE_SETTLEMENT")
    expected={s["provider"].casefold():s["fixture_id"] for s in f["sources"]}
    if type(results) is not list or len(results)!=2:raise ValueError("TWO_RESULTS_REQUIRED")
    seen=set();scores=[];times=[]
    for s in results:
        fields(s,"provider fixture_id home away kickoff_utc observed_utc status score")
        provider=identifier(s["provider"]).casefold()
        if provider in seen or provider not in expected or identifier(s["fixture_id"])!=expected[provider]:
            raise ValueError("RESULT_NATIVE_ID_MISMATCH")
        seen.add(provider)
        if (s["home"],s["away"],instant(s["kickoff_utc"]),s["status"])!=(f["home"],f["away"],ko,"FINAL_REGULATION"):
            raise ValueError("RESULT_FIXTURE_MISMATCH")
        stamp=instant(s["observed_utc"])
        if not ko+timedelta(minutes=120)<=stamp<=now:raise ValueError("RESULT_CLOCK")
        score=s["score"]
        if type(score) is not list or len(score)!=2 or any(type(v) is not int or not 0<=v<=30 for v in score):
            raise ValueError("RESULT_SCORE")
        scores.append(score);times.append(stamp)
    if scores[0]!=scores[1]:raise ValueError("RESULT_DISAGREEMENT")
    x,y=scores[0];k=0 if x>y else 1 if x==y else 2
    metrics={}
    for name in MODELS:
        model=record["models"][name]
        grid=score_matrix(*model["goal_rates"])
        if digest(grid)!=model["score_matrix_sha256"]:raise ValueError("MATRIX_MISMATCH")
        p=model["probabilities_1x2"]
        u=math.fsum(v for i,r in enumerate(grid) for j,v in enumerate(r) if i+j<=2)
        m={"1x2_log_loss":-math.log(max(p[k],1e-15)),
           "1x2_brier":math.fsum((v-(i==k))**2 for i,v in enumerate(p)),
           "under25_brier":(u-(x+y<=2))**2}
        for label,market,side,line in MARKETS:
            m[label+"_grade_brier"]=grade_brier(grid,x,y,market,side,line)
        metrics[name]=m
    out={"protocol":PROTOCOL,"league":record["league"],"fixture_key":record["fixture_key"],
         "kickoff_utc":ko.isoformat(),"forecast_sha256":envelope["record_sha256"],
         "result_observations_sha256":digest(results),"checked_utc":now.isoformat(),
         "score":[x,y],"metrics":metrics,"local_replay_consistent":True,
         "two_declared_results_agree":True,"external_timestamp_attested":False,
         "independent_result_authenticated":False,"authenticated_forward_samples":0,
         "actual_market_quotes_verified":False,"positive_ev_verified":False,
         "production_recommendations":"DISABLED","status":"HOLD"}
    return {"record":out,"record_sha256":digest(out)}

def aggregate(cases,*,now=None):
    # Revalidate original inputs and source results on every run; no admission
    # from previously computed or caller-supplied metric summaries.
    now=now or datetime.now(timezone.utc)
    if type(cases) is not list or len(cases)>MAX_CASES:raise ValueError("CASE_SCOPE")
    rows=[];seen=set();native=set()
    for c in cases:
        fields(c,"original forecast results")
        r=settle(c["original"],c["forecast"],c["results"],now=now)["record"]
        if r["fixture_key"] in seen:raise ValueError("DUPLICATE_SETTLEMENT")
        seen.add(r["fixture_key"])
        ids={(s["provider"].casefold(),s["fixture_id"]) for s in c["original"]["fixture"]["sources"]}
        if native&ids:raise ValueError("REUSED_NATIVE_ID")
        native.update(ids);rows.append(r)
    groups=defaultdict(list)
    for r in rows:groups[r["league"]].append(r)
    def summarize(rs):
        n=len(rs);weeks=defaultdict(list)
        for r in rs:
            weeks[instant(r["kickoff_utc"]).isocalendar()[:2]].append(r["metrics"]["baseline"]["1x2_log_loss"]-r["metrics"]["blend_50"]["1x2_log_loss"])
        coverage=n>=300 and len(weeks)>=12
        stats={}
        for m in METRICS:
            b=math.fsum(r["metrics"]["baseline"][m] for r in rs)
            c=math.fsum(r["metrics"]["blend_50"][m] for r in rs)
            stats[m]={"baseline":b/n if n else None,"blend_50":c/n if n else None,
                      "baseline_minus_candidate":(b-c)/n if n else None}
        return {"n":n,"week_blocks":len(weeks),"metrics":stats,
                "primary_descriptive_ci95":paired_ci([(math.fsum(v),len(v)) for _,v in sorted(weeks.items())]) if coverage else None}
    return {"protocol":PROTOCOL,"recorded_local_cases":len(rows),"pooled":summarize(rows),
            "by_league":{k:summarize(v) for k,v in sorted(groups.items())},
            "complete_attempt_denominator_verified":False,"local_consistency_not_authentication":True,
            "authenticated_forward_samples":0,"independent_prospective_validation":False,
            "actual_market_quotes_verified":False,"positive_ev_verified":False,
            "production_recommendations":"DISABLED","status":"HOLD"}

def audit_sealed_cohort(cohort,cases,*,now=None):
    """Reconcile a caller-supplied local seal roster; not a complete universe."""
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError("NAIVE_NOW")
    now=now.astimezone(timezone.utc)
    if type(cohort) is not list or len(cohort)>MAX_CASES:
        raise ValueError("COHORT_SCOPE")
    if type(cases) is not list or len(cases)>MAX_CASES:
        raise ValueError("CASE_SCOPE")
    roster={};native=set()
    for item in cohort:
        fields(item,"original forecast")
        envelope=item["forecast"]
        fields(envelope,"record record_sha256")
        r=envelope["record"]
        if digest(r)!=envelope["record_sha256"]:
            raise ValueError("RECORD_DIGEST_MISMATCH")
        captured=instant(r["captured_utc"])
        if captured>now or digest(seal(item["original"],now=captured))!=digest(envelope):
            raise ValueError("COHORT_SEAL_REPLAY_MISMATCH")
        key=r["fixture_key"]
        if key in roster:raise ValueError("DUPLICATE_COHORT_FIXTURE")
        ids={(s["provider"].casefold(),s["fixture_id"]) for s in r["fixture"]["sources"]}
        if native&ids:raise ValueError("REUSED_COHORT_NATIVE_ID")
        native.update(ids)
        roster[key]=(envelope["record_sha256"],instant(r["fixture"]["kickoff_utc"]),r["league"])
    submitted=set()
    for c in cases:
        fields(c,"original forecast results")
        envelope=c["forecast"];fields(envelope,"record record_sha256")
        key=envelope["record"]["fixture_key"]
        if key not in roster or roster[key][0]!=envelope["record_sha256"]:
            raise ValueError("SETTLEMENT_OUTSIDE_SEALED_COHORT")
        if key in submitted:raise ValueError("DUPLICATE_SETTLEMENT")
        submitted.add(key)
    summary=aggregate(cases,now=now)
    buckets=defaultdict(lambda:{"declared_seals":0,"settled":0,
                                "not_yet_mature":0,"mature_unsettled":0})
    for key,(_,ko,league) in roster.items():
        b=buckets[league];b["declared_seals"]+=1
        state=("settled" if key in submitted else
               "mature_unsettled" if now>=ko+timedelta(minutes=120) else "not_yet_mature")
        b[state]+=1
    totals={k:sum(b[k] for b in buckets.values()) for k in
            ("declared_seals","settled","not_yet_mature","mature_unsettled")}
    if (totals["declared_seals"]!=totals["settled"]+totals["not_yet_mature"]+totals["mature_unsettled"]
            or totals["settled"]!=summary["recorded_local_cases"]):
        raise ValueError("COHORT_ACCOUNTING")
    return {"protocol":PROTOCOL,"checked_utc":now.isoformat(),
            "local_roster_sha256":digest(sorted((k,v[0]) for k,v in roster.items())),
            "counts":totals,"by_league":dict(sorted(buckets.items())),
            "local_paired_evaluation":summary,
            "declared_roster_reconciled":True,
            "complete_attempt_denominator_verified":False,
            "selection_bias_ruled_out":False,"external_timestamp_attested":False,
            "authenticated_forward_samples":0,"independent_prospective_validation":False,
            "positive_ev_verified":False,"production_recommendations":"DISABLED","status":"HOLD"}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",required=True);p.add_argument("--output",required=True)
    p.add_argument("--cohort",help="Optional caller-supplied original seal roster JSON")
    a=p.parse_args()
    cases=load(a.input)
    result=audit_sealed_cohort(load(a.cohort),cases) if a.cohort else aggregate(cases)
    with Path(a.output).open("x",encoding="utf-8") as f:json.dump(result,f,sort_keys=True,allow_nan=False)
if __name__=="__main__":main()
