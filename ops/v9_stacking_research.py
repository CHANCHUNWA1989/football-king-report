"""V10.1 chronological stacked probability challenger (research only).
Base predictions are retrospective prior-season/prior-day reconstructions.
No executable market, xG or independently attested clocks are implied.
"""
import math
from datetime import date
from ops import v5_ensemble_competition as e
from ops import v8_multiseason as v

EXPERTS=(*e.NAMES,"v8")
TRAIN=("2022-23","2023-24")
CAL="2024-25"
TEST="2025-26"
TEMPS=(.8,1.,1.2,1.5)
MIX=(0.,.25,.5,.75,1.)
MIN_ROWS=200

def features(row):
    q=[e.vec(row["experts"][k]) for k in EXPERTS]
    if set(row["experts"])!=set(EXPERTS):raise ValueError("EXPERT_SET")
    # Fixed log-probability ratios relative to draw; no outcome feature.
    return [math.log(max(p[i],1e-9)/max(p[1],1e-9)) for p in q for i in (0,2)]

def temper(p,t):
    if t not in TEMPS:raise ValueError("TEMPERATURE")
    z=[math.log(max(x,1e-15))/t for x in e.vec(p)]
    m=max(z);w=[math.exp(x-m) for x in z]
    return e.vec([x/sum(w) for x in w])

def combine(p,reference,t,w):
    if w not in MIX:raise ValueError("MIX")
    return e.vec([(1-w)*a+w*b for a,b in zip(e.vec(reference),temper(p,t))])

def partition(rows):
    buckets={"train":[],"cal":[],"test":[]};seen=set()
    for row in rows:
        k=(row["league"],*e.key(row))
        d=date.fromisoformat(row["date"])
        if k in seen or row["league"] not in v.LEAGUES or type(row["y"]) is not int or row["y"] not in (0,1,2):
            raise ValueError("INVALID_STACK_CASE")
        seen.add(k)
        season=row["season"]
        if season not in (*TRAIN,CAL,TEST):raise ValueError("STACK_SEASON")
        year=int(season[:4])
        if not date(year,7,1)<=d<date(year+1,7,1):raise ValueError("STACK_SEASON_CLOCK")
        features(row);e.vec(row["candidate"]);e.vec(row["hybrid"])
        buckets["train" if season in TRAIN else "cal" if season==CAL else "test"].append(row)
    for part in buckets.values():
        part.sort(key=lambda r:(r["date"],r["league"],r["home"],r["away"]))
    return buckets

def fit_stack(rows):
    from sklearn.linear_model import LogisticRegression
    if len(rows)<MIN_ROWS or {r["y"] for r in rows}!={0,1,2}:raise ValueError("STACK_TRAIN_COVERAGE")
    if any(r["season"] not in TRAIN for r in rows):raise ValueError("STACK_TRAIN_SCOPE")
    model=LogisticRegression(C=.1,max_iter=1000,random_state=42)
    model.fit([features(r) for r in rows],[r["y"] for r in rows])
    if list(model.classes_)!=[0,1,2] or max(model.n_iter_)>=1000:raise ValueError("STACK_FIT_FAILED")
    return model

def select_calibration(rows,predictions):
    if len(rows)<MIN_ROWS or len(rows)!=len(predictions) or {r["y"] for r in rows}!={0,1,2}:
        raise ValueError("STACK_CAL_COVERAGE")
    if any(r["season"]!=CAL for r in rows):raise ValueError("STACK_CAL_SCOPE")
    def objective(pair):
        t,w=pair
        loss=math.fsum(e.loss(combine(p,r["candidate"],t,w),r["y"]) for p,r in zip(predictions,rows))/len(rows)
        return (loss+.005*w*w+.001*(t-1)**2,w,abs(t-1),t)
    return min(((t,w) for t in TEMPS for w in MIX),key=objective)

def report(rows,totals):
    from ops.v9_league_weights import ci
    parts=partition(rows)
    model=fit_stack(parts["train"])
    def probabilities(part):
        return [e.vec([float(x) for x in p]) for p in model.predict_proba([features(r) for r in part])]
    t,w=select_calibration(parts["cal"],probabilities(parts["cal"]))
    test=parts["test"]
    if len(test)<MIN_ROWS or {r["y"] for r in test}!={0,1,2}:raise ValueError("STACK_TEST_COVERAGE")
    scored=[{**r,"stack":combine(p,r["candidate"],t,w),"raw_stack":p} for r,p in zip(test,probabilities(test))]
    def metrics(a,total):
        if not a or len(a)>total:raise ValueError("STACK_SCOPE")
        m={k:e.metrics(a,lambda r:r[k]) for k in ("hybrid","candidate","raw_stack","stack")}
        interval=ci([{**r,"hybrid":r["candidate"],"candidate":r["stack"]} for r in a])
        common=[r for r in a if max(r["candidate"])>=.5]
        return {"n":len(a),"all_finished":total,"coverage":len(a)/total,"metrics":m,
                "same_v10_selected_n":len(common),
                "same_v10_selected":{k:e.metrics(common,lambda r:r[k]) for k in ("candidate","stack")},
                "paired_week_ci_v10_minus_stack":interval,
                "historical_proper_score_gate":bool(interval and interval[0]>0 and all(m["stack"][k]<m["candidate"][k] for k in ("log_loss","brier")))}
    return {"schema":"v10-1-chronological-stacking-research-v1","training_n":len(parts["train"]),
            "calibration_n":len(parts["cal"]),"assessment_n":len(test),
            "training_seasons":TRAIN,"calibration_season":CAL,"assessment_season":TEST,
            "selected_temperature":t,"selected_stack_weight":w,"grid_size":len(TEMPS)*len(MIX),
            "meta_features":16,"logistic_C":.1,"pooled":metrics(scored,sum(totals.values())),
            "per_league":{k:metrics([r for r in scored if r["league"]==k],totals[k]) for k in v.LEAGUES},
            "assessment_previously_inspected":True,"prospective_validation":False,
            "verified_forward_sample_credit":0,"automatic_promotion":False,
            "production_recommendations":"DISABLED","status":"HOLD"}
