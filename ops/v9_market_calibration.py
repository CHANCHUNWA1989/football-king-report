"""V14 market-consensus calibration, not executable quotes or EV.
Pinned retrospective archive has no independent outcome receipt timestamps.
A 72h chronological embargo is precautionary, NOT clock attestation.
"""
import math
from datetime import datetime,timedelta,timezone
from ops import v5_ensemble_competition as e
from ops.v9_league_weights import ci
from ops.market_shrinkage import blend
from ops.v5_ucl_source_gate import utc

SHARES=(0.,.125,.25)
TEMPS=(.9,1.,1.1)
MODES=("constant","disagreement_damped")
MIN_DEV=50
MIN_TEST=30
EMBARGO=timedelta(hours=72)

def disagreement(r):
    p,m=blend(r["p"],r["m"],0.),blend(r["p"],r["m"],1.)
    return math.fsum(abs(a-b) for a,b in zip(p,m))/2

def probability(r,share,temp,mode):
    if share not in SHARES or temp not in TEMPS or mode not in MODES:
        raise ValueError("MARKET_PARAMETER")
    # Bound influence when model and market disagree. Not a learned live signal.
    effective=share if mode=="constant" else share*(1-disagreement(r))
    p=blend(r["p"],r["m"],1-effective)
    if temp==1.:return p
    z=[math.log(max(x,1e-15))/temp for x in p]
    q=[math.exp(x-max(z)) for x in z]
    return e.vec([x/math.fsum(q) for x in q])

def fit(dev):
    if len(dev)<MIN_DEV or {r["y"] for r in dev}!={0,1,2}:
        raise ValueError("MARKET_DEV_COVERAGE")
    def objective(par):
        w,t,mode=par
        loss=math.fsum(e.loss(probability(r,*par),r["y"]) for r in dev)/len(dev)
        penalty=.02*w*w+.02*(t-1)**2
        return loss+penalty,w,abs(t-1),mode
    return min(((w,t,m) for w in SHARES for t in TEMPS for m in MODES),key=objective)

def evaluate(rows,split_day):
    split=datetime.fromisoformat(split_day).replace(tzinfo=timezone.utc)
    seen=set()
    for r in rows:
        if r["key"] in seen or type(r["y"]) is not int or r["y"] not in (0,1,2):
            raise ValueError("MARKET_CASE")
        seen.add(r["key"])
        if not utc(r["market_utc"])<=utc(r["forecast_utc"])<utc(r["kickoff"]):
            raise ValueError("MARKET_CLOCK")
    dev=[r for r in rows if utc(r["kickoff"])<split-EMBARGO]
    test=[r for r in rows if utc(r["kickoff"])>=split]
    result={"schema":"v14-consensus-calibration-research-v1","split_utc":split.isoformat(),
            "embargo_hours":72,"development_n":len(dev),"assessment_n":len(test),
            "embargo_excluded_n":len(rows)-len(dev)-len(test),"selected_parameters":None,
            "metrics":None,"outcome_availability_attested":False,
            "raw_bookmaker_quotes_available":False,"market_time_series_available":False,
            "assessment_previously_inspected":True,"verified_forward_sample_credit":0,
            "verified_ev":False,"automatic_promotion":False,"production_recommendations":"DISABLED","status":"HOLD"}
    if len(dev)<MIN_DEV or len(test)<MIN_TEST or {r["y"] for r in dev}!={0,1,2} or {r["y"] for r in test}!={0,1,2}:
        return {**result,"reason":"INSUFFICIENT_COHORT"}
    par=fit(dev)
    scored=[{**r,"date":utc(r["kickoff"]).date().isoformat(),"hybrid":blend(r["p"],r["m"],1.),
             "candidate":probability(r,*par),"model":blend(r["p"],r["m"],0.)} for r in test]
    def metrics(a):
        return {k:e.metrics(a,lambda r:r[k]) for k in ("model","hybrid","candidate")}
    m=metrics(scored);interval=ci(scored)
    bands={}
    for name,pred in (("low_disagreement",lambda r:disagreement(r)<.10),
                      ("high_disagreement",lambda r:disagreement(r)>=.10),
                      ("age_le_1h",lambda r:utc(r["forecast_utc"])-utc(r["market_utc"])<=timedelta(hours=1)),
                      ("age_gt_1h",lambda r:utc(r["forecast_utc"])-utc(r["market_utc"])>timedelta(hours=1))):
        a=[r for r in scored if pred(r)]
        bands[name]={"n":len(a),"metrics":metrics(a) if len(a)>=10 else None}
    return {**result,"selected_parameters":{"model_share":par[0],"temperature":par[1],"mode":par[2]},
            "grid_size":len(SHARES)*len(TEMPS)*len(MODES),"metrics":m,"diagnostic_bands":bands,
            "paired_week_ci_market_minus_candidate":interval,
            "historical_proper_score_gate":bool(interval and interval[0]>0 and all(m["candidate"][k]<m["hybrid"][k] for k in ("log_loss","brier"))),
            "reason":"RETROSPECTIVE_CONSENSUS_ONLY"}
