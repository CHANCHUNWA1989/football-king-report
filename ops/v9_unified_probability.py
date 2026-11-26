"""V16 minimum-KL outcome-mass reconciliation of a prematch score PMF.
Preserves conditional score probabilities within each 1X2 outcome. Not an
inverse estimate of goal rates. No executable odds or authenticated forecasts.
"""
import math
from ops import v5_ensemble_competition as e
from ops.v5_integration_acceptance import grid,project,settlement,GRADES

LINES=(("handicap","home",-.25),("handicap","home",-.75),
       ("handicap","away",.25),("totals","over",2.25),("totals","over",2.75))
THRESHOLDS=(.45,.5,.6,.7)
CLASSES=(0,1,2)

def outcome(h,a):
    return 0 if h>a else 1 if h==a else 2

def mass(g):
    if type(g) is not dict or not 1<=len(g)<=4356:raise ValueError("SCORE_GRID")
    for k,v in g.items():
        if type(k) is not tuple or len(k)!=2 or any(type(i) is not int or not 0<=i<=65 for i in k):
            raise ValueError("SCORE_INDEX")
        if type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1:raise ValueError("SCORE_MASS")
    if abs(math.fsum(g.values())-1)>1e-10:raise ValueError("SCORE_MASS")
    return [math.fsum(v for (h,a),v in g.items() if outcome(h,a)==i) for i in CLASSES]

def reconcile(g,target):
    before=mass(g);p=e.vec(target)
    if any(x<=0 and y>0 for x,y in zip(before,p)):raise ValueError("UNSUPPORTED_OUTCOME_MASS")
    factors=[y/x if x>0 else 0. for x,y in zip(before,p)]
    out={(h,a):v*factors[outcome(h,a)] for (h,a),v in g.items()}
    if any(abs(x-y)>1e-10 for x,y in zip(mass(out),p)):raise ValueError("RECONCILIATION_MISMATCH")
    return out

def base_grid(h,a):
    if any(type(x) not in (int,float) or not math.isfinite(x) or not .1<=x<=5.5 for x in (h,a)):
        raise ValueError("SCORE_RATES")
    g=grid(0,0,h,a);rho=-.05
    tau={(0,0):1-h*a*rho,(0,1):1+h*rho,(1,0):1+a*rho,(1,1):1-rho}
    out={k:v*tau.get(k,1.) for k,v in g.items()}
    z=math.fsum(out.values());out={k:v/z for k,v in out.items()}
    mass(out);return out

def distribution_metrics(rows):
    n=len(rows)
    if not n:raise ValueError("EMPTY_SCORE_COHORT")
    score_loss=math.fsum(-math.log(max(r["grid"].get(r["actual"],0.),1e-15)) for r in rows)/n
    score_brier=math.fsum(math.fsum(p*p for p in r["grid"].values())-2*r["grid"].get(r["actual"],0.)+1 for r in rows)/n
    return {"n":n,"exact_score_log_loss":score_loss,"exact_score_brier":score_brier,
            "exact_score_top_correct":sum(max(r["grid"],key=r["grid"].get)==r["actual"] for r in rows),
            "one_x_two":e.metrics(rows,lambda r:mass(r["grid"])),
            "hypothetical_lines":[{"market":kind,"side":side,"line":line,
                "five_grade_brier":math.fsum(math.fsum((p[g]-(g==settlement(*r["actual"],kind,side,line)))**2 for g in GRADES)
                    for r,p in ((r,project(r["grid"],kind,side,line)) for r in rows))/n}
                for kind,side,line in LINES]}

def evaluate(raw,scored):
    actual={};seen=set()
    for d,h,a,ch,ca,x,y,season in raw:
        if season!="2025-26":continue
        k=(d.isoformat(),h,a)
        if k in actual:raise ValueError("DUPLICATE_SCORE")
        actual[k]=(x,y)
    if len(actual)!=144 or len(scored)!=144:raise ValueError("SCORE_COHORT")
    buckets={k:[] for k in ("raw_dc","reference_reconciled","hurdle_reconciled")}
    for r in scored:
        k=e.key(r)
        if k in seen or k not in actual or r["y"]!=outcome(*actual[k]):raise ValueError("SCORE_PAIR")
        seen.add(k)
        base=base_grid(r["home_rate"],r["away_rate"])
        for name,g in (("raw_dc",base),("reference_reconciled",reconcile(base,r["reference"])),
                       ("hurdle_reconciled",reconcile(base,r["candidate"]))):
            buckets[name].append({"grid":g,"actual":actual[k],"y":r["y"]})
    if seen!=actual.keys():raise ValueError("MISSING_SCORE_PAIR")
    # Fixed thresholds, descriptive only, never selected using assessment labels.
    coverage=[]
    for t in THRESHOLDS:
        picked=[r for r in scored if max(r["candidate"])>=t]
        coverage.append({"threshold":t,"n":len(picked),"coverage":len(picked)/len(scored),
                         "metrics":e.metrics(picked,lambda r:r["candidate"])})
    return {"schema":"v16-unified-outcome-mass-research-v1","assessment_n":len(scored),
        "metrics":{k:distribution_metrics(v) for k,v in buckets.items()},
        "fixed_threshold_diagnostics":coverage,"conditional_score_shape_preserved":True,
        "score_grid_reconciled":True,"goal_rates_reverse_inferred":False,
        "hypothetical_lines_only":True,"actual_market_quotes":False,
        "assessment_previously_inspected":True,"confidence_threshold_validated":False,
        "verified_forward_sample_credit":0,"verified_ev":False,"automatic_promotion":False,
        "production_recommendations":"DISABLED","status":"HOLD"}
