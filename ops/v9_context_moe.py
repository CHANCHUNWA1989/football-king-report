"""V11.3 context-gated nine-expert prematch probability research.
Fit gate on reconstructed development predictions; separate calibration and
assessment seasons. In-play experts intentionally excluded (no paired archive).
"""
import math
from ops import v5_ensemble_competition as e,v8_multiseason as v
from ops.v9_stacking_research import (partition,fit_stack,select_calibration,
                                     features as stack_features,combine,MIN_ROWS)
from ops.v9_league_weights import ANCHOR
from ops.v9_bayesian_state import replay

NAMES=(*e.NAMES,"v8","bayes")
PRIOR=tuple(.8*ANCHOR[k] for k in NAMES[:-1])+(.2,)
REG=.02
GRID=(0.,.25,.5,.75,1.)
DIM=1+len(v.LEAGUES)+4

def probabilities(r):
    if set(r["experts"])!=set(NAMES[:-1]):raise ValueError("MOE_EXPERT_SET")
    return [e.vec(r["experts"][k]) for k in NAMES[:-1]]+[e.vec(r["bayes"])]

def context(r):
    ps=probabilities(r);ref=e.vec(r["candidate"])
    if r["league"] not in v.LEAGUES:raise ValueError("MOE_LEAGUE")
    spread=sum(max(p[i] for p in ps)-min(p[i] for p in ps) for i in range(3))/3
    entropy=-sum(x*math.log(max(x,1e-15)) for x in ref)/math.log(3)
    return [1.]+[float(r["league"]==k) for k in v.LEAGUES]+[max(ref),ref[1],spread,entropy]

def matrices(rows):
    import numpy as np
    return np.asarray([context(r) for r in rows],dtype=float),np.asarray([probabilities(r) for r in rows],dtype=float)

def gate_weights(x,theta):
    import numpy as np
    z=x@theta+np.log(np.asarray(PRIOR))
    z-=z.max(axis=1,keepdims=True)
    w=np.exp(z);return w/w.sum(axis=1,keepdims=True)

def fit_gate(rows):
    import numpy as np
    from scipy.optimize import minimize
    if len(rows)<MIN_ROWS or {r["y"] for r in rows}!={0,1,2} or any(r["season"] not in ("2022-23","2023-24") for r in rows):
        raise ValueError("MOE_TRAIN_SCOPE")
    x,p=matrices(rows);n=len(rows)
    py=p[np.arange(n),:,[r["y"] for r in rows]]
    def objective(flat):
        theta=flat.reshape(DIM,len(NAMES));w=gate_weights(x,theta)
        mass=(w*py).sum(axis=1)
        if (mass<=0).any():raise ValueError("MOE_ZERO_LIKELIHOOD")
        loss=-np.log(mass).mean()+REG*np.sum(theta*theta)/2
        dz=w*(1-py/mass[:,None])
        grad=x.T@dz/n+REG*theta
        return float(loss),grad.ravel()
    result=minimize(objective,np.zeros(DIM*len(NAMES)),jac=True,method="L-BFGS-B",
                    options={"maxiter":500,"ftol":1e-10})
    if not result.success or not np.isfinite(result.x).all():raise ValueError("MOE_FIT_FAILED")
    return result.x.reshape(DIM,len(NAMES))

def infer(rows,theta):
    import numpy as np
    x,p=matrices(rows);w=gate_weights(x,theta)
    return [e.vec(list(map(float,a))) for a in np.sum(p*w[:,:,None],axis=1)],w

def mix(a,b,w):
    if w not in GRID:raise ValueError("MOE_MIX")
    return e.vec([(1-w)*x+w*y for x,y in zip(e.vec(a),e.vec(b))])

def calibrate(rows,stack,gate):
    if len(rows)<MIN_ROWS or len(rows)!=len(stack) or len(rows)!=len(gate) or any(r["season"]!="2024-25" for r in rows):
        raise ValueError("MOE_CAL_SCOPE")
    return min(GRID,key=lambda w:(math.fsum(e.loss(mix(s,g,w),r["y"]) for r,s,g in zip(rows,stack,gate))/len(rows)+.005*w*w,w))

def report(data,rows,totals):
    from ops.v9_league_weights import ci
    parts=partition(rows);index={}
    for league in v.LEAGUES:
        for old,new in zip(v.SEASONS,v.SEASONS[1:]):
            for r in replay(data[old,league],data[new,league],league,new):
                k=(league,*e.key(r))
                if k in index:raise ValueError("MOE_DUPLICATE_BAYES")
                index[k]=r
    for key,part in parts.items():
        joined=[]
        for r in part:
            other=index.get((r["league"],*e.key(r)))
            if other is None or other["y"]!=r["y"] or other["season"]!=r["season"]:raise ValueError("MOE_PAIR_MISMATCH")
            joined.append({**r,"bayes":other["bayes"]})
        parts[key]=joined
    tr,cal,test=(parts[k] for k in ("train","cal","test"))
    if len(test)<MIN_ROWS or {r["y"] for r in test}!={0,1,2}:raise ValueError("MOE_TEST_COVERAGE")
    theta=fit_gate(tr);stack_model=fit_stack(tr)
    def raw_stack(a):
        return [e.vec(list(map(float,p))) for p in stack_model.predict_proba([stack_features(r) for r in a])]
    cal_raw=raw_stack(cal);t,sw=select_calibration(cal,cal_raw)
    cal_stack=[combine(p,r["candidate"],t,sw) for r,p in zip(cal,cal_raw)]
    cal_gate,_=infer(cal,theta)
    weight=calibrate(cal,cal_stack,cal_gate)
    stack=[combine(p,r["candidate"],t,sw) for r,p in zip(test,raw_stack(test))]
    gate,weights=infer(test,theta)
    scored=[{**r,"stack":s,"gate":g,"moe":mix(s,g,weight)} for r,s,g in zip(test,stack,gate)]
    def metrics(a,total):
        if not a or len(a)>total:raise ValueError("MOE_COVERAGE")
        m={k:e.metrics(a,lambda r:r[k]) for k in ("candidate","stack","bayes","gate","moe")}
        interval=ci([{**r,"hybrid":r["stack"],"candidate":r["moe"]} for r in a])
        return {"n":len(a),"all_finished":total,"coverage":len(a)/total,"metrics":m,
                "paired_week_ci_stack_minus_moe":interval,
                "historical_proper_score_gate":bool(interval and interval[0]>0 and all(m["moe"][k]<m["stack"][k] for k in ("log_loss","brier")))}
    return {"schema":"v11-3-context-gated-nine-expert-research-v1","expert_names":NAMES,
            "context_dimension":DIM,"gate_parameter_count":DIM*len(NAMES),"regularization":REG,
            "training_n":len(tr),"calibration_n":len(cal),"assessment_n":len(test),
            "selected_moe_weight":weight,"stack_temperature":t,"stack_weight":sw,
            "mean_gate_weights":{k:float(weights[:,i].mean()) for i,k in enumerate(NAMES)},
            "pooled":metrics(scored,sum(totals.values())),
            "per_league":{k:metrics([r for r in scored if r["league"]==k],totals[k]) for k in v.LEAGUES},
            "assessment_previously_inspected":True,"inplay_experts_included":False,
            "market_odds_used":False,"actual_xg_used":False,"prospective_validation":False,
            "verified_forward_sample_credit":0,"automatic_promotion":False,
            "production_recommendations":"DISABLED","status":"HOLD"}
