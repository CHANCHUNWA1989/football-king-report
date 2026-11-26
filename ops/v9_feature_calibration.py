"""Independent xG/xGA and lineup research challengers, no authorized data bundled.
Same-fixture chronological comparison; no invented xG, no automatic promotion.
"""
import argparse
import json
import math
from pathlib import Path
from datetime import datetime,timezone
from ops import v9_xg_research as xg,v9_lineup_research as xi
from ops import v5_ensemble_competition as e
from ops.v6_forward_bundle import decode
from ops.v5_ucl_source_gate import utc
from ops.v9_league_weights import ci

HALF_LIFE=120.
SHRINK=8.
WEIGHTS=(0.,.25,.5,.75,1.)
COEFFICIENTS=(0.,.25,.5,1.,2.)
MIN_TRAIN=100
MIN_TEST=50
MIN_CHANGED_TRAIN=50
MIN_CHANGED_TEST=25
MAX_XG_ROWS=5000

def rates(history,h,a,day,key):
    if any(r["ko"].date()>=day.date() or r["available"]>=day for r in history):
        raise ValueError("XG_FUTURE_HISTORY")
    if len(history)<20:return None
    n=gf=ga=0.
    stats={h:[0.,0.,0.,0],a:[0.,0.,0.,0]}
    for r in history:
        w=2**(-(day-r["ko"]).total_seconds()/86400/HALF_LIFE)
        x,y=r[key];n+=w;gf+=w*x;ga+=w*y
        for t,f,g in ((r["home"],x,y),(r["away"],y,x)):
            if t in stats:
                s=stats[t];s[0]+=w;s[1]+=w*f;s[2]+=w*g;s[3]+=1
    if min(s[3] for s in stats.values())<5:return None
    lh=(gf+20*1.5)/(n+20);la=(ga+20*1.2)/(n+20);mu=(lh+la)/2
    def team(t):
        z,f,g,_=stats[t]
        return (f+SHRINK*mu)/(z+SHRINK)/mu,(g+SHRINK*mu)/(z+SHRINK)/mu
    ah,dh=team(h);aa,da=team(a)
    return max(.1,min(5.5,lh*ah*da)),max(.1,min(5.5,la*aa*dh))

def xg_cases(rows):
    if len(rows)>MAX_XG_ROWS:raise ValueError("XG_REPLAY_LIMIT")
    out=[]
    for r in rows:
        hist=[s for s in rows if s["ko"].date()<r["ko"].date() and s["available"]<r["ko"]]
        g=rates(hist,r["home"],r["away"],r["ko"],"goals")
        x=rates(hist,r["home"],r["away"],r["ko"],"xg")
        if g is None or x is None:continue
        h,a=r["goals"]
        out.append({**r,"date":r["ko"].date().isoformat(),"y":0 if h>a else 1 if h==a else 2,
                    "goal_rates":g,"xg_rates":x,"baseline":e.dc(*g)})
    return out

def xg_predict(r,w):
    if w not in WEIGHTS:raise ValueError("XG_WEIGHT")
    if w==0.:return e.dc(*r["goal_rates"])
    if w==1.:return e.dc(*r["xg_rates"])
    return e.dc(*[math.exp((1-w)*math.log(g)+w*math.log(x)) for g,x in zip(r["goal_rates"],r["xg_rates"])])

def lineup_predict(r,b):
    if b not in COEFFICIENTS:raise ValueError("XI_COEFFICIENT")
    delta=r["rating_delta"]
    if type(delta) not in (int,float) or not math.isfinite(delta) or not -4<=delta<=4:raise ValueError("XI_DELTA")
    z=max(-.5,min(.5,b*delta));p=e.vec(r["baseline"])
    q=[p[0]*math.exp(z),p[1],p[2]*math.exp(-z)]
    return e.vec([v/sum(q) for v in q])

def evaluate(rows,split,end,kind):
    if not split<end:raise ValueError("SPLIT_ORDER")
    if len({r["id"] for r in rows})!=len(rows):raise ValueError("DUPLICATE_CASE")
    train=[r for r in rows if r["ko"]<split and r["available"]<split]
    test=[r for r in rows if split<=r["ko"]<end and r["available"]<end]
    result={"schema":"v13-feature-calibration-research-v1","kind":kind,"training_n":len(train),
            "assessment_n":len(test),"split_utc":split.isoformat(),"assessment_end_utc":end.isoformat(),
            "metrics":None,"selected_parameter":None,"verified_forward_sample_credit":0,
            "source_and_clock_authenticated":False,"prospective_validation":False,
            "production_recommendations":"DISABLED","automatic_promotion":False,"status":"HOLD"}
    if kind=="xg":grid=WEIGHTS;fn=xg_predict;penalty=.005
    elif kind=="lineup":grid=COEFFICIENTS;fn=lineup_predict;penalty=.002
    else:raise ValueError("UNKNOWN_FEATURE_KIND")
    if len(train)<MIN_TRAIN or len(test)<MIN_TEST or {r["y"] for r in train}!={0,1,2} or {r["y"] for r in test}!={0,1,2}:
        return {**result,"reason":"INSUFFICIENT_CHRONOLOGICAL_COHORT"}
    if kind=="lineup" and (sum(r["changes"]>0 for r in train)<MIN_CHANGED_TRAIN or sum(r["changes"]>0 for r in test)<MIN_CHANGED_TEST):
        return {**result,"reason":"INSUFFICIENT_CHANGED_XI"}
    param=min(grid,key=lambda p:(math.fsum(e.loss(fn(r,p),r["y"]) for r in train)/len(train)+penalty*p*p,p))
    scored=[{**r,"hybrid":r["baseline"],"candidate":fn(r,param)} for r in test]
    m={k:e.metrics(scored,lambda r:r[k]) for k in ("baseline","candidate")}
    interval=ci(scored)
    return {**result,"selected_parameter":param,"metrics":m,"paired_week_ci_baseline_minus_candidate":interval,
            "historical_proper_score_gate":bool(interval and interval[0]>0 and all(m["candidate"][k]<m["baseline"][k] for k in ("log_loss","brier"))),
            "assessment_previously_inspected_unknown":True,
            "reason":"RESEARCH_ONLY_UNAUTHENTICATED"}

def main():
    p=argparse.ArgumentParser();p.add_argument("--kind",choices=("xg","lineup"),required=True)
    for k in ("capture","metadata","split","end","output"):p.add_argument("--"+k,required=True)
    a=p.parse_args();f=Path(a.capture);m=Path(a.metadata)
    adapter=xg if a.kind=="xg" else xi
    if not 0<f.stat().st_size<=adapter.MAX_BYTES or not 0<m.stat().st_size<=100000:raise ValueError("SIZE")
    meta=decode(m.read_bytes())
    # Single competition declared by data owner, not independently verified.
    scope=meta.get("competition_scope")
    if not isinstance(scope,str) or not scope.strip() or len(scope)>128:raise ValueError("COMPETITION_SCOPE_REQUIRED")
    now=datetime.now(timezone.utc);split,end=utc(a.split),utc(a.end)
    if end>now:raise ValueError("FUTURE_ASSESSMENT")
    rows=adapter.load(f.read_bytes(),meta,now)
    if a.kind=="xg":rows=xg_cases(rows)
    out=evaluate(rows,split,end,a.kind);out["declared_competition_scope"]=scope
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
