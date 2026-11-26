"""Frozen probability risk overlays; no modification of production probabilities.
Calibrate on early 2024-25, check late 2024-25, assess previously inspected 2025-26.
The anchor itself used full 2024-25 calibration; no independent validation.
"""
import argparse,json,math
from collections import defaultdict
from datetime import date,datetime,timedelta
from pathlib import Path
from ops.v29_xg_residual import checked,read
from ops.v8_multiseason import PIN,LEAGUES
from ops.v9_lineup_research import probability
from ops.v5_ensemble_competition import metrics

DRAW_GRID=(.03,.05,.08,.10,.12,.15,.20)
CONF_GRID=(.45,.50,.55,.60,.65,.70)
def flags(p,draw_gap,confidence):
    p=probability(p)
    return {"draw_risk":None if draw_gap is None else max(p)-p[1]<=draw_gap,
            "high_confidence_research":None if confidence is None else max(p)>=confidence,
            "probability":p,"production_recommendations":"DISABLED","status":"HOLD"}

def hit(r):return max(range(3),key=lambda i:r["stack"][i])==r["y"]
def stats(rows,rule):
    a=[r for r in rows if rule(r["stack"])]
    b=[r for r in rows if not rule(r["stack"])]
    return {"n":len(a),"correct":sum(map(hit,a)),"draws":sum(r["y"]==1 for r in a),
            "draw_rate":sum(r["y"]==1 for r in a)/len(a) if a else None,
            "accuracy":sum(map(hit,a))/len(a) if a else None,"coverage":len(a)/len(rows),
            "unflagged_n":len(b),"unflagged_accuracy":sum(map(hit,b))/len(b) if b else None,
            "all_draw_rate":sum(r["y"]==1 for r in rows)/len(rows),
            "all_accuracy":sum(map(hit,rows))/len(rows)}
def risk(t):return lambda p:max(p)-p[1]<=t
def high(t):return lambda p:max(p)>=t

def evaluate(doc):
    if doc.get("schema")!="v29-stack-reference-v1" or doc.get("historical_source_commit")!=PIN or doc.get("status")!="HOLD" or doc.get("production_recommendations")!="DISABLED" or doc.get("verified_forward_sample_credit")!=0:raise ValueError("ANCHOR_CONTRACT")
    early=[];late=[];test=[];seen=set()
    for r in doc["rows"]:
        d=date.fromisoformat(r["date"]);key=(r["league"],r["date"],r["home"],r["away"])
        if key in seen or r["league"] not in LEAGUES or type(r["y"]) is not int or r["y"] not in (0,1,2):raise ValueError("CASE_IDENTITY")
        seen.add(key);probability(r["stack"])
        if r["season"]=="2024-25" and date(2024,7,1)<=d<date(2025,7,1):
            (early if d<date(2025,1,1) else late).append(r)
        elif r["season"]=="2025-26" and date(2025,7,1)<=d<date(2026,7,1):test.append(r)
        else:raise ValueError("SEASON_CLOCK")
    if any(len(a)<100 or {r["y"] for r in a}!={0,1,2} for a in (early,late,test)):raise ValueError("INSUFFICIENT_COHORT")
    candidates=[]
    for t in DRAW_GRID:
        a=stats(early,risk(t))
        if a["n"]>=50 and a["coverage"]<=.4 and a["draw_rate"]>=a["all_draw_rate"]+.05:candidates.append((a["draw_rate"],-t))
    t=-max(candidates)[1] if candidates else None
    validation=stats(late,risk(t)) if t is not None else None
    if validation is None or validation["n"]<50 or validation["draw_rate"]<validation["all_draw_rate"]+.03:t=None
    candidates=[]
    for u in CONF_GRID:
        a=stats(early,high(u))
        if a["n"]>=100 and a["coverage"]>=.25 and a["accuracy"]>=a["all_accuracy"]+.05:candidates.append((a["accuracy"],-u))
    u=-max(candidates)[1] if candidates else None
    validation_high=stats(late,high(u)) if u is not None else None
    if validation_high is None or validation_high["n"]<100 or validation_high["coverage"]<.25 or validation_high["accuracy"]<validation_high["all_accuracy"]+.05:u=None
    # Rolling diagnostic uses only dates before the evaluation day; no probability change.
    days=defaultdict(list)
    for r in test:days[date.fromisoformat(r["date"])].append(r)
    history=[];watch=[]
    for d,batch in sorted(days.items()):
        prev=[r for r in history if d-timedelta(days=28)<=date.fromisoformat(r["date"])<d]
        if len(prev)>=50:
            a=sum(map(hit,prev))/len(prev)
            expected=sum(max(r["stack"]) for r in prev)/len(prev)
            if a<expected-.10:watch.append({"date":d.isoformat(),"history_n":len(prev),"accuracy":a,"mean_top_probability":expected})
        history.extend(batch)
    return {"schema":"stress-repair-risk-overlay-v1","early_n":len(early),"late_n":len(late),"assessment_n":len(test),
            "baseline":metrics(test,lambda r:r["stack"]),"draw_gap":t,"draw_validation":validation,
            "draw_assessment":stats(test,risk(t)) if t is not None else None,"confidence_threshold":u,
            "confidence_validation":validation_high,"confidence_assessment":stats(test,high(u)) if u is not None else None,
            "drift_watch_days":watch,"drift_threshold":.10,"history_days":28,"minimum_history":50,
            "prior_day_only":True,"result_availability_independently_verified":False,"probabilities_modified":False,
            "assessment_previously_inspected":True,"calibration_reused_for_anchor":True,"automatic_promotion":False,
            "verified_forward_sample_credit":0,"production_recommendations":"DISABLED","status":"HOLD"}
def main():
    p=argparse.ArgumentParser()
    for k in ("anchor","sha256","output"):p.add_argument("--"+k,required=True)
    a=p.parse_args();d=evaluate(checked(read(a.anchor),a.sha256))
    with Path(a.output).open("x") as f:json.dump(d,f,indent=2,allow_nan=False)
    print(json.dumps(d,allow_nan=False))
if __name__=="__main__":main()
