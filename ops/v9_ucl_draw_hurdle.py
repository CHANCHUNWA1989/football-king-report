"""V15 UCL draw hurdle and conditional decisive-outcome calibration.
Development-only grid, same inspected assessment as the goal-strength reference.
No hard draw quota, market odds, current forecasts or promotion.
"""
import math
from datetime import date
from itertools import product
from ops import v8_ucl_calibration as c,v5_ensemble_competition as e
from ops.v9_ucl_goal_strength import replay,mix,BLENDS
from ops.v9_league_weights import ci

SHIFTS=(-.3,0.,.3)
SLOPES=(-.3,0.,.3)
TEMPS=(.8,1.,1.2)
PENALTY=.04

def logit(p):
    p=max(1e-12,min(1-1e-12,p))
    return math.log(p)-math.log1p(-p)

def sigmoid(z):
    return 1/(1+math.exp(-max(-40.,min(40.,z))))

def predict(r,par):
    d,t,g,s=par
    if d not in SHIFTS or t not in SLOPES or g not in SLOPES or s not in TEMPS:
        raise ValueError("HURDLE_PARAMS")
    p=e.vec(r["reference"])
    h,a=r["home_rate"],r["away_rate"]
    if any(type(x) not in (int,float) or not math.isfinite(x) or not .1<=x<=5.5 for x in (h,a)):
        raise ValueError("HURDLE_RATES")
    if par==(0.,0.,0.,1.):return p
    # Draw odds conditional on total scoring intensity and absolute imbalance.
    total=max(-1.,min(1.,(h+a-2.7)/2.7))
    gap=min(1.,abs(math.log(h/a)))
    draw=sigmoid(logit(p[1])+d+t*total+g*gap)
    # Preserve the ordering of home/away conditional on a decisive result.
    decisive=p[0]+p[2]
    home=sigmoid(logit(p[0]/decisive if decisive else .5)/s)
    return e.vec([(1-draw)*home,draw,(1-draw)*(1-home)])

def fit(rows):
    if len(rows)<200 or {r["y"] for r in rows}!={0,1,2} or any(r["season"] not in c.DEV or r["date"]>="2025-07-01" for r in rows):
        raise ValueError("HURDLE_DEVELOPMENT")
    def objective(par):
        d,t,g,s=par
        penalty=d*d+t*t+g*g+(s-1)**2
        loss=math.fsum(e.loss(predict(r,par),r["y"]) for r in rows)/len(rows)
        return loss+PENALTY*penalty,penalty,par
    return min(product(SHIFTS,SLOPES,SLOPES,TEMPS),key=objective)

def diagnostic(rows,key):
    n=len(rows)
    if not n:return None
    draw_obs=sum(r["y"]==1 for r in rows)
    # "Underdog" is the less probable of the two decisive sides in the
    # fixed reference, NOT a bookmaker-defined outsider.
    def outsider(r):return 0 if r["reference"][0]<r["reference"][2] else 2
    eligible=[r for r in rows if abs(r["reference"][0]-r["reference"][2])>1e-12]
    return {"n":n,"draw_observed":draw_obs,"mean_draw_probability":math.fsum(r[key][1] for r in rows)/n,
            "draw_binary_brier":math.fsum((r[key][1]-(r["y"]==1))**2 for r in rows)/n,
            "draw_top_count":sum(max(range(3),key=lambda j:r[key][j])==1 for r in rows),
            "draw_top_correct":sum(r["y"]==1 and max(range(3),key=lambda j:r[key][j])==1 for r in rows),
            "reference_outsider_n":len(eligible),
            "reference_outsider_observed":sum(r["y"]==outsider(r) for r in eligible),
            "reference_outsider_mean_probability":math.fsum(r[key][outsider(r)] for r in eligible)/len(eligible) if eligible else None,
            "reference_outsider_binary_brier":math.fsum((r[key][outsider(r)]-(r["y"]==outsider(r)))**2 for r in eligible)/len(eligible) if eligible else None}

def evaluate(raw,adaptive_rows):
    idx={(r["date"],r["home"],r["away"]):r for r in replay(raw)}
    rows=[];seen=set()
    for r in adaptive_rows:
        if r["season"] not in (*c.DEV,c.TEST):continue
        k=(r["date"],r["home"],r["away"]);q=idx.get(k)
        if k in seen or q is None or q["season"]!=r["season"] or q["y"]!=r["y"]:raise ValueError("HURDLE_PAIR")
        seen.add(k)
        rows.append({**r,**{k:q[k] for k in ("goal_strength","home_rate","away_rate")}})
    dev=[r for r in rows if r["season"] in c.DEV];test=[r for r in rows if r["season"]==c.TEST]
    if len(dev)!=336 or len(test)!=144:raise ValueError("HURDLE_COHORT")
    old=c.fit([{**r,"hybrid":r["adaptive"]} for r in dev])
    new=c.fit([{**r,"hybrid":r["goal_strength"]} for r in dev])
    def prepare(r):
        return {**r,"old":c.calibrate(r["adaptive"],*old),"new":c.calibrate(r["goal_strength"],*new)}
    dev=list(map(prepare,dev));test=list(map(prepare,test))
    w=min(BLENDS,key=lambda w:(math.fsum(e.loss(mix(r["old"],r["new"],w),r["y"]) for r in dev)/len(dev)+.005*w*w,w))
    def reference(r):return {**r,"reference":mix(r["old"],r["new"],w)}
    dev=list(map(reference,dev));test=list(map(reference,test))
    par=fit(dev)
    scored=[{**r,"candidate":predict(r,par),"hybrid":r["reference"]} for r in test]
    metrics={k:e.metrics(scored,lambda r:r[k]) for k in ("reference","candidate")}
    interval=ci(scored)
    bands={}
    for name,a in (("low_rate",[r for r in scored if r["home_rate"]+r["away_rate"]<2.5]),
                   ("high_rate",[r for r in scored if r["home_rate"]+r["away_rate"]>=2.5]),
                   ("close_rates",[r for r in scored if abs(math.log(r["home_rate"]/r["away_rate"]))<.3])):
        bands[name]={"n":len(a),"diagnostics":{k:diagnostic(a,k) for k in ("reference","candidate")} if len(a)>=10 else None}
    from ops.v9_unified_probability import evaluate as unified_evaluate
    unified=unified_evaluate(raw,scored)
    return {"v16_unified_probability":unified,"schema":"v15-ucl-draw-hurdle-research-v1","development_n":len(dev),"assessment_n":len(test),
        "reference_strength_weight":w,"parameters":{"draw_intercept":par[0],"total_rate_slope":par[1],"imbalance_slope":par[2],"decisive_temperature":par[3]},
        "grid_size":81,"metrics":metrics,"class_profiles":{k:c.profile(scored,lambda r:r[k]) for k in ("reference","candidate")},
        "diagnostics":{k:diagnostic(scored,k) for k in ("reference","candidate")},"bands":bands,
        "paired_week_ci_reference_minus_candidate":interval,
        "historical_proper_score_gate":bool(interval and interval[0]>0 and all(metrics["candidate"][k]<metrics["reference"][k] for k in ("log_loss","brier"))),
        "assessment_previously_inspected":True,"draw_quota":False,"reference_outsider_is_bookmaker_underdog":False,
        "score_grid_reconciled":False,"current_fixture_forecasts":0,"verified_forward_sample_credit":0,
        "automatic_promotion":False,"production_recommendations":"DISABLED","status":"HOLD"}
