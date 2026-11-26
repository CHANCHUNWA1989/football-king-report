"""V18 causal league-level model competition, research only.
Fixed rolling eligibility and reversible quarantine; dates only, not attested
result receipts. The stack anchor always retains at least half the mass.
"""
import math
from collections import defaultdict,deque,Counter
from ops import v5_ensemble_competition as e,v8_multiseason as v
from ops import v9_stacking_research as s
from ops.v9_league_weights import ci

NAMES=("stack","v8","ensemble","candidate")
SHORT=24
LONG=96
MIN_HISTORY=48
ENTER=.01
EXIT=.025
MAX_SHARE=.5
TEMPERATURE=4.

def loss_delta(r,k):
    return e.loss(r["stack"],r["y"])-e.loss(r[k],r["y"])

def decision(history,previous):
    if len(history)<MIN_HISTORY:
        return {"stack":1.,**{k:0. for k in NAMES[1:]}},dict.fromkeys(NAMES[1:],False),False
    short=history[-SHORT:];long=history[-LONG:]
    recent={k:math.fsum(loss_delta(r,k) for r in short)/len(short) for k in NAMES[1:]}
    overall={k:math.fsum(loss_delta(r,k) for r in long)/len(long) for k in NAMES[1:]}
    active={}
    for k in NAMES[1:]:
        if previous.get(k,False):
            active[k]=recent[k]>=-EXIT and overall[k]>=-EXIT
        else:
            active[k]=recent[k]>0 and overall[k]>ENTER
    raw={k:math.exp(TEMPERATURE*min(1.,overall[k])) for k in active if active[k]}
    weights={k:0. for k in NAMES};weights["stack"]=1.
    if raw:
        total=math.fsum(raw.values())
        weights["stack"]=1-MAX_SHARE
        for k,z in raw.items():weights[k]=MAX_SHARE*z/total
    earlier=history[-2*SHORT:-SHORT]
    drift=(math.fsum(e.loss(r["stack"],r["y"]) for r in short)/len(short)-
           math.fsum(e.loss(r["stack"],r["y"]) for r in earlier)/len(earlier))>.15
    return weights,active,drift

def replay(rows):
    groups=defaultdict(list);seen=set()
    for r in rows:
        k=(r["league"],*e.key(r))
        if k in seen or r["league"] not in v.LEAGUES or r["season"]!=s.TEST or not "2025-07-01"<=r["date"]<"2026-07-01" or type(r["y"]) is not int or r["y"] not in (0,1,2):
            raise ValueError("COMPETITION_CASE")
        seen.add(k)
        groups[(r["league"],r["date"])].append({**r,**{name:e.vec(r[name]) for name in NAMES}})
    hist=defaultdict(lambda:deque(maxlen=LONG));state=defaultdict(dict);out=[]
    for (league,day),batch in sorted(groups.items()):
        previous=state[league];history=list(hist[league])
        weights,active,drift=decision(history,previous)
        transitions={k:("ADMITTED" if active[k] else "QUARANTINED") for k in active if active[k]!=previous.get(k,False)}
        batch=sorted(batch,key=e.key)
        for i,r in enumerate(batch):
            p=e.vec([math.fsum(weights[k]*r[k][j] for k in NAMES) for j in range(3)])
            out.append({**r,"competition":p,"weights":dict(weights),"prior_n":len(history),
                        "anchor_drift_flag":drift,"transitions":transitions if i==0 else {}})
        state[league]=active;hist[league].extend(batch)
    return out

def report(rows,totals):
    parts=s.partition(rows)
    model=s.fit_stack(parts["train"])
    def raw(a):return [e.vec([float(x) for x in p]) for p in model.predict_proba([s.features(r) for r in a])]
    t,w=s.select_calibration(parts["cal"],raw(parts["cal"]))
    test=parts["test"]
    if len(test)<s.MIN_ROWS or {r["y"] for r in test}!={0,1,2}:raise ValueError("COMPETITION_COVERAGE")
    scored=replay([{**r,"stack":s.combine(p,r["candidate"],t,w)} for r,p in zip(test,raw(test))])
    def metrics(a,total):
        if not a or len(a)>total:raise ValueError("COMPETITION_DENOMINATOR")
        m={k:e.metrics(a,lambda r:r[k]) for k in (*NAMES,"competition")}
        interval=ci([{**r,"hybrid":r["stack"],"candidate":r["competition"]} for r in a])
        changed=[r for r in a if r["weights"]["stack"]<1.]
        return {"n":len(a),"coverage":len(a)/total,"metrics":m,
                "adaptive_n":len(changed),"adaptive_same_fixture":{k:e.metrics(changed,lambda r:r[k]) for k in ("stack","competition")},
                "anchor_drift_flagged_n":sum(r["anchor_drift_flag"] for r in a),
                "transitions":dict(Counter(k+":"+status for r in a for k,status in r["transitions"].items())),
                "mean_weights":{k:math.fsum(r["weights"][k] for r in a)/len(a) for k in NAMES},
                "paired_week_ci_stack_minus_competition":interval,
                "historical_proper_score_gate":bool(interval and interval[0]>0 and all(m["competition"][k]<m["stack"][k] for k in ("log_loss","brier")))}
    return {"schema":"v18-causal-model-competition-research-v1","assessment_n":len(scored),
            "stack_temperature":t,"stack_weight":w,"short_window":SHORT,"long_window":LONG,
            "minimum_history":MIN_HISTORY,"entry_loss_advantage":ENTER,"exit_loss_tolerance":EXIT,
            "minimum_anchor_weight":1-MAX_SHARE,"pooled":metrics(scored,sum(totals.values())),
            "per_league":{k:metrics([r for r in scored if r["league"]==k],totals[k]) for k in v.LEAGUES},
            "prior_calendar_day_only":True,"assessment_previously_inspected":True,
            "result_receipt_times_attested":False,"drift_flag_descriptive_only":True,
            "production_model_switching":False,"prospective_validation":False,
            "verified_forward_sample_credit":0,"automatic_promotion":False,
            "production_recommendations":"DISABLED","status":"HOLD"}
