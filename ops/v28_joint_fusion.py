"""V28 conservative joint fusion of existing trained challengers.
Fit all learners in 2022-24; calibrate joint weights in 2024-25.
The assessment is previously inspected, not a fresh independent holdout.
No live deployment, market or foundation-model weights are implied.
"""
import math
from itertools import product
from ops import v9_stacking_research as s,v9_context_moe as moe
from ops import v26_nonlinear_meta as meta,v9_bayesian_state as bayes
from ops import v5_ensemble_competition as e,v8_multiseason as v
from ops.v9_league_weights import ci

NAMES=("bayes","nonlinear","gate")
UNITS=tuple(q for q in product(range(3),repeat=3) if sum(q)<=3)
TEMPS=(.8,1.,1.2)
RULES=tuple((q,t) for q in UNITS for t in TEMPS if sum(q) or t==1.)
def fuse(r,rule):
    if rule not in RULES:raise ValueError("FUSION_RULE")
    units,t=rule
    a=e.vec(r["stack"]);b=[s.temper(r[k],t) for k in NAMES]
    if not sum(units):return a
    return e.vec([(1-sum(units)/8)*a[i]+math.fsum(u*p[i]/8 for u,p in zip(units,b)) for i in range(3)])
def select(rows):
    if len(rows)<s.MIN_ROWS or {r["y"] for r in rows}!={0,1,2} or any(r["season"]!=s.CAL or not "2024-07-01"<=r["date"]<"2025-07-01" for r in rows):
        raise ValueError("FUSION_CAL_SCOPE")
    def objective(rule):
        q,t=rule;share=sum(q)/8
        return (math.fsum(e.loss(fuse(r,rule),r["y"]) for r in rows)/len(rows)+.02*share**2+.002*(t-1)**2,share,abs(t-1),q,t)
    return min(RULES,key=objective)
def report(data,rows,totals):
    parts=s.partition(rows);index={}
    for league in v.LEAGUES:
        for old,new in zip(v.SEASONS,v.SEASONS[1:]):
            for r in bayes.replay(data[old,league],data[new,league],league,new):
                k=(league,*e.key(r))
                if k in index:raise ValueError("FUSION_DUPLICATE_BAYES")
                index[k]=r
    for key,part in parts.items():
        joined=[]
        for r in part:
            other=index.get((r["league"],*e.key(r)))
            if other is None or other["y"]!=r["y"] or other["season"]!=r["season"]:raise ValueError("FUSION_PAIR_MISMATCH")
            joined.append({**r,"bayes":other["bayes"]})
        parts[key]=joined
    tr,cal,test=(parts[k] for k in ("train","cal","test"))
    if len(test)<s.MIN_ROWS or {r["y"] for r in test}!={0,1,2}:raise ValueError("FUSION_TEST_SCOPE")
    anchor=s.fit_stack(tr);nonlinear=meta.fit(tr);theta=moe.fit_gate(tr)
    def raw(m,a,fn):return [e.vec([float(x) for x in p]) for p in m.predict_proba([fn(r) for r in a])]
    t,sw=s.select_calibration(cal,raw(anchor,cal,s.features))
    def predict(a):
        stack=[s.combine(p,r["candidate"],t,sw) for r,p in zip(a,raw(anchor,a,s.features))]
        n=raw(nonlinear,a,meta.features);g,_=moe.infer(a,theta)
        return [{**r,"stack":p,"nonlinear":q,"gate":z} for r,p,q,z in zip(a,stack,n,g)]
    dev=predict(cal);rule=select(dev)
    out=[{**r,"fusion":fuse(r,rule)} for r in predict(test)]
    def evaluate(a,total):
        if not a or len(a)>total:raise ValueError("FUSION_COHORT")
        m={k:e.metrics(a,lambda r:r[k]) for k in ("stack",*NAMES,"fusion")}
        interval=ci([{**r,"hybrid":r["stack"],"candidate":r["fusion"]} for r in a])
        return {"n":len(a),"all_finished":total,"coverage":len(a)/total,"metrics":m,
                "paired_week_ci_stack_minus_fusion":interval,
                "historical_proper_score_gate":bool(sum(rule[0]) and interval and interval[0]>0 and all(m["fusion"][k]<m["stack"][k] for k in ("log_loss","brier")))}
    return {"schema":"v28-joint-fusion-research-v1","training_n":len(tr),"calibration_n":len(cal),"assessment_n":len(test),
        "grid_size":len(RULES),"selected_weights":{"stack":1-sum(rule[0])/8,**{k:u/8 for k,u in zip(NAMES,rule[0])}},
        "selected_challenger_temperature":rule[1],"maximum_challenger_share":.375,
        "pooled":evaluate(out,sum(totals.values())),"per_league":{k:evaluate([r for r in out if r["league"]==k],totals[k]) for k in v.LEAGUES},
        "assessment_previously_inspected":True,"calibration_reused_for_anchor_and_fusion":True,"market_odds_used":False,
        "tabpfn_used":False,"actual_xg_used":False,"inplay_used":False,"prospective_validation":False,
        "verified_forward_sample_credit":0,"automatic_promotion":False,"production_recommendations":"DISABLED","status":"HOLD"}
