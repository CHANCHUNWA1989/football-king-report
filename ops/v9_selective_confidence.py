"""V17 chronological selective confidence research, domestic same-fixture cohort.
Separate calibration and rule selection. No guarantee of risk control under
dependent football results; Wilson intervals are descriptive iid approximations.
"""
import math
from itertools import product
from ops import v5_ensemble_competition as e,v8_multiseason as v
from ops import v9_stacking_research as s

CUT="2025-01-01"
RULES=tuple(product((.50,.55,.60,.65,.70),(0.,.10),(.15,1.)))
TARGET=.70
MIN_N=100
MIN_COVERAGE=.15

def features(r,p):
    p=e.vec(p);ordered=sorted(p,reverse=True)
    a,b=e.vec(r["ensemble"]),e.vec(r["v8"])
    return {**r,"p":p,"confidence":ordered[0],"margin":ordered[0]-ordered[1],
            "disagreement":math.fsum(abs(x-y) for x,y in zip(a,b))/2}

def select(rows,rule):
    if rule not in RULES:raise ValueError("CONFIDENCE_RULE")
    t,m,d=rule
    return [r for r in rows if r["confidence"]>=t and r["margin"]>=m and r["disagreement"]<=d]

def lower(correct,n):
    if not n:return None
    p=correct/n;z=1.959963984540054
    return max(0.,(p+z*z/(2*n)-z*math.sqrt(p*(1-p)/n+z*z/(4*n*n)))/(1+z*z/n))

def summary(rows,total):
    if not total or len(rows)>total:raise ValueError("CONFIDENCE_DENOMINATOR")
    n=len(rows);hits=sum(max(range(3),key=lambda i:r["p"][i])==r["y"] for r in rows)
    return {"n":n,"correct":hits,"accuracy":hits/n if n else None,"coverage":n/total,
            "mean_confidence":math.fsum(r["confidence"] for r in rows)/n if n else None,
            "wilson_lower_95_descriptive":lower(hits,n),"proper_scores":e.metrics(rows,lambda r:r["p"])}

def qualifies(m):
    return m["n"]>=MIN_N and m["coverage"]>=MIN_COVERAGE and m["accuracy"]>=TARGET and m["wilson_lower_95_descriptive"]>=.60

def choose(rows):
    if not rows or any(r["season"]!=s.CAL or not CUT<=r["date"]<"2025-07-01" for r in rows):
        raise ValueError("CONFIDENCE_RULE_SCOPE")
    options=[]
    for rule in RULES:
        m=summary(select(rows,rule),len(rows))
        if qualifies(m):options.append((-m["n"],-m["accuracy"],rule))
    return min(options)[2] if options else None

def reliability(rows):
    bins=[]
    for i in range(10):
        a=[r for r in rows if min(9,int(r["confidence"]*10))==i]
        if a:
            m=summary(a,len(rows))
            bins.append({"low":i/10,"high":(i+1)/10,"n":len(a),"accuracy":m["accuracy"],"mean_confidence":m["mean_confidence"]})
    return {"bins":bins,"ece":math.fsum(b["n"]*abs(b["accuracy"]-b["mean_confidence"]) for b in bins)/len(rows) if rows else None}

def report(rows,totals):
    parts=s.partition(rows)
    early=[r for r in parts["cal"] if r["date"]<CUT]
    late=[r for r in parts["cal"] if r["date"]>=CUT]
    if min(len(early),len(late),len(parts["test"]))<s.MIN_ROWS or any({r["y"] for r in a}!={0,1,2} for a in (early,late,parts["test"])):
        raise ValueError("CONFIDENCE_COHORT")
    model=s.fit_stack(parts["train"])
    def raw(a):return [e.vec([float(x) for x in p]) for p in model.predict_proba([s.features(r) for r in a])]
    t,w=s.select_calibration(early,raw(early))
    def scored(a):return [features(r,s.combine(p,r["candidate"],t,w)) for r,p in zip(a,raw(a))]
    dev=scored(late);test=scored(parts["test"])
    rule=choose(dev);picked=select(test,rule) if rule else []
    total=sum(totals.values())
    m=summary(picked,total)
    return {"schema":"v17-domestic-selective-confidence-research-v1","training_n":len(parts["train"]),
        "probability_calibration_n":len(early),"rule_selection_n":len(dev),"assessment_eligible_n":len(test),
        "assessment_all_finished":total,"calibration_rule_cut":CUT,"temperature":t,"stack_weight":w,
        "rules_count":len(RULES),"chosen_rule":rule,"development_selected":summary(select(dev,rule),len(dev)) if rule else None,
        "assessment_selected":m,"assessment_all_eligible":summary(test,total),
        "assessment_reliability":reliability(test),"target_accuracy":TARGET,"min_selected":MIN_N,"min_coverage":MIN_COVERAGE,
        "historical_point_gate":bool(rule and qualifies(m)),
        "fixed_threshold_diagnostics":[{"rule":q,"assessment":summary(select(test,q),total)} for q in RULES if q[1:]==(0.,1.)],
        "per_league":{k:summary([r for r in picked if r["league"]==k],totals[k]) for k in v.LEAGUES},
        "assessment_previously_inspected":True,"wilson_not_dependence_adjusted":True,"coverage_rule_dev_denominator_eligible_only":True,
        "risk_control_guaranteed":False,"prospective_validation":False,"verified_forward_sample_credit":0,
        "automatic_promotion":False,"production_recommendations":"DISABLED","status":"HOLD"}
