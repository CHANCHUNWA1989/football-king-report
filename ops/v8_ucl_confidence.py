"""V8.9 UCL selective confidence research; no betting or automatic promotion."""
import argparse,json
from itertools import product
from pathlib import Path
from ops import v8_ucl_strength as u,v8_ucl_gap_fill as g,v8_ucl_opponent as o,v8_ucl_calibration as c
from ops import v5_ensemble_competition as e
from ops.v6_forward_bundle import decode

THRESHOLDS=(.50,.55,.60,.65,.70)
MARGINS=(0.,.10,.20)
DIVERGENCES=(.10,.20,1.)
RULES=tuple(product(THRESHOLDS,MARGINS,DIVERGENCES,(False,True)))
MIN_N=100
MIN_COVERAGE=.25
TARGET=.70

def top(p):return max(range(3),key=lambda i:p[i])
def features(r,params):
    p=c.calibrate(r["hybrid"],*params)
    a,b=e.vec(r["baseline"]),e.vec(r["elo"])
    ordered=sorted(p,reverse=True)
    return {**r,"p":p,"confidence":ordered[0],"margin":ordered[0]-ordered[1],
        "tv":sum(abs(x-y) for x,y in zip(a,b))/2,"agreement":top(a)==top(b)==top(p)}
def select(rows,rule):
    t,m,d,agree=rule
    return [r for r in rows if r["confidence"]>=t and r["margin"]>=m and r["tv"]<=d and (not agree or r["agreement"])]
def report(rows,all_n):
    n=len(rows)
    if not all_n or n>all_n:raise ValueError("BAD_DENOMINATOR")
    correct=sum(top(r["p"])==r["y"] for r in rows)
    return {"n":n,"correct":correct,"accuracy":correct/n if n else None,
        "coverage":n/all_n,"proper_scores":e.metrics(rows,lambda r:r["p"])}
def qualifies(r):
    return r["n"]>=MIN_N and r["coverage"]>=MIN_COVERAGE and r["accuracy"]>=TARGET
def choose(dev):
    if any(r["season"] not in c.DEV or r["date"]>="2025-07-01" for r in dev):raise ValueError("ASSESSMENT_LEAKAGE")
    if not dev:raise ValueError("EMPTY_DEV")
    options=[]
    for rule in RULES:
        r=report(select(dev,rule),len(dev))
        if qualifies(r):options.append((-r["n"],-r["accuracy"],rule))
    # Max coverage first, then accuracy, deterministic lexicographic tie break.
    return min(options)[2] if options else None
def evaluate(rows):
    seen=set()
    for r in rows:
        k=(r["date"],r["home"],r["away"])
        if k in seen or type(r["y"]) is not int or r["y"] not in (0,1,2):raise ValueError("INVALID_CASE")
        seen.add(k)
    dev=[r for r in rows if r["season"] in c.DEV]
    test=[r for r in rows if r["season"]==c.TEST]
    if len(dev)!=336 or len(test)!=144 or any(r["date"]<"2025-07-01" for r in test):raise ValueError("COHORT")
    params=c.fit(dev)
    dev=[features(r,params) for r in dev];test=[features(r,params) for r in test]
    rule=choose(dev)
    d=report(select(dev,rule),len(dev)) if rule else None
    t=report(select(test,rule),len(test)) if rule else None
    # Fixed diagnostic rules, never use assessment to select a rule.
    diagnostic=[{"rule":list(q),"development":report(select(dev,q),len(dev)),
        "assessment":report(select(test,q),len(test))} for q in [(v,0.,1.,False) for v in THRESHOLDS]]
    return {"schema":"v8-9-ucl-selective-confidence-research-v1","development_n":len(dev),"assessment_n":len(test),
        "calibration_parameters":list(params),"fixed_rules_count":len(RULES),"chosen_rule":list(rule) if rule else None,
        "development_selected":d,"assessment_selected":t,"assessment_all":report(test,len(test)),
        "fixed_threshold_diagnostics":diagnostic,"development_calibration_and_rule_selection_share_samples":True,
        "target_accuracy":TARGET,"minimum_selected":MIN_N,"minimum_coverage":MIN_COVERAGE,
        "historical_point_gate":bool(t and qualifies(t)),"statistical_promotion_gate":False,
        "assessment_previously_inspected":True,"prospective_validation":False,"verified_forward_sample_credit":0,
        "current_fixture_forecasts":0,"production_recommendations":"DISABLED","automatic_promotion":False,"status":"HOLD"}
def main():
    p=argparse.ArgumentParser()
    for k in ("input-dir","manifest","old-dir","old-manifest","output"):p.add_argument("--"+k,required=True)
    a=p.parse_args()
    old,_=u.load(a.old_dir,decode(Path(a.old_manifest).read_bytes()))
    new,_=g.load(a.input_dir,decode(Path(a.manifest).read_bytes()))
    if sorted(r for r in old if r[-1]=="2024-25")!=sorted(r for r in new if r[-1]=="2024-25"):raise ValueError("OVERLAP_CONFLICT")
    rows=sorted([r for r in old if r[-1]!="2024-25"]+new)
    if len(rows)!=1536:raise ValueError("COHORT_SIZE")
    out=evaluate(o.replay(rows))
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
