"""V26 regularized nonlinear meta-learner challenge, no automatic promotion.
Identical historical cases as V10.1, fit/calibration only before assessment.
No external data, new independent holdout, or probability superiority claim.
"""
import math
from itertools import product
from ops import v9_stacking_research as s,v5_ensemble_competition as e,v8_multiseason as v
from ops.v9_league_weights import ci

TEMPS=(.8,1.,1.2,1.5)
SHARES=(0.,.125,.25,.5,1.)

def features(r):
    q=[e.vec(r["experts"][k]) for k in s.EXPERTS]
    ref=e.vec(r["candidate"])
    spread=[max(p[i] for p in q)-min(p[i] for p in q) for i in range(3)]
    return s.features(r)+ref+spread+[-math.fsum(x*math.log(max(x,1e-15)) for x in ref)]

def blend(anchor,challenger,t,w):
    if t not in TEMPS or w not in SHARES:raise ValueError("META_GRID")
    a=e.vec(anchor);b=s.temper(challenger,t)
    return a if w==0 else e.vec([(1-w)*x+w*y for x,y in zip(a,b)])

def fit(rows):
    from catboost import CatBoostClassifier
    if len(rows)<s.MIN_ROWS or {r["y"] for r in rows}!={0,1,2} or any(r["season"] not in s.TRAIN for r in rows):
        raise ValueError("META_TRAIN_SCOPE")
    m=CatBoostClassifier(loss_function="MultiClass",iterations=180,depth=3,learning_rate=.025,l2_leaf_reg=12,
        random_seed=42,thread_count=1,verbose=False,allow_writing_files=False)
    m.fit([features(r) for r in rows],[r["y"] for r in rows])
    if list(m.classes_)!=[0,1,2]:raise ValueError("META_CLASS_ORDER")
    return m

def select(rows,anchor,challenge):
    if len(rows)<s.MIN_ROWS or len(rows)!=len(anchor) or len(rows)!=len(challenge) or {r["y"] for r in rows}!={0,1,2} or any(r["season"]!=s.CAL for r in rows):
        raise ValueError("META_CAL_SCOPE")
    def objective(p):
        t,w=p
        return (math.fsum(e.loss(blend(a,b,t,w),r["y"]) for r,a,b in zip(rows,anchor,challenge))/len(rows)
                +.01*w*w+.002*(t-1)**2,w,abs(t-1),t)
    return min(product(TEMPS,SHARES),key=objective)

def report(rows,totals):
    parts=s.partition(rows);base=s.fit_stack(parts["train"]);challenger=fit(parts["train"])
    def raw(m,a,fn):return [e.vec([float(x) for x in p]) for p in m.predict_proba([fn(r) for r in a])]
    t,w=s.select_calibration(parts["cal"],raw(base,parts["cal"],s.features))
    def anchor(a):return [s.combine(p,r["candidate"],t,w) for r,p in zip(a,raw(base,a,s.features))]
    cal=parts["cal"];test=parts["test"]
    ct,cw=select(cal,anchor(cal),raw(challenger,cal,features))
    scored=[{**r,"stack":a,"nonlinear":b,"challenger":blend(a,b,ct,cw)}
            for r,a,b in zip(test,anchor(test),raw(challenger,test,features))]
    def evaluate(a):
        m={k:e.metrics(a,lambda r:r[k]) for k in ("stack","nonlinear","challenger")}
        interval=ci([{**r,"hybrid":r["stack"],"candidate":r["challenger"]} for r in a])
        return {"n":len(a),"metrics":m,"paired_week_ci_stack_minus_challenger":interval,
            "historical_proper_score_gate":bool(interval and interval[0]>0 and all(m["challenger"][k]<m["stack"][k] for k in ("log_loss","brier")))}
    return {"schema":"v26-nonlinear-meta-research-v1","training_n":len(parts["train"]),"calibration_n":len(cal),
        "assessment_n":len(test),"features_n":23,"selected_temperature":ct,"selected_challenger_share":cw,
        "grid_size":len(TEMPS)*len(SHARES),"pooled":evaluate(scored),
        "per_league":{k:evaluate([r for r in scored if r["league"]==k]) for k in v.LEAGUES},
        "assessment_previously_inspected":True,"prospective_validation":False,
        "verified_forward_sample_credit":0,"automatic_promotion":False,"production_recommendations":"DISABLED","status":"HOLD"}
