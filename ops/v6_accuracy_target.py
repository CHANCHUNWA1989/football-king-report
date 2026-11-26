"""V6.3 historical 70% 1X2 target, fixed development-only selection.
Not a betting or production recommendation system. No promotion.
"""
import argparse
from collections import defaultdict
from datetime import date
import json
import math
from pathlib import Path
import random
from ops import v5_ensemble_competition as e
from ops.v6_calibration_challenger import WEIGHTS,CUT

TARGET=.70
THRESHOLDS=(.45,.50,.55,.60,.65,.70,.75,.80)
MIN_DEV=50
MIN_COVERAGE=.20
MIN_ASSESSMENT=100

def summary(rows,threshold=None):
    a=[r for r in rows if threshold is None or max(r["base"])>=threshold]
    return {"n":len(a),"population_n":len(rows),"coverage":len(a)/len(rows) if rows else None,
        "accuracy":sum(max(range(3),key=lambda i:r["base"][i])==r["y"] for r in a)/len(a) if a else None,
        "metrics":e.metrics(a,lambda r:r["base"])}

def select(dev):
    if any(r["date"]>=CUT for r in dev):raise ValueError("ASSESSMENT_LEAKAGE")
    if not dev:return None
    for t in THRESHOLDS:
        s=summary(dev,t)
        if s["n"]>=MIN_DEV and s["coverage"]>=MIN_COVERAGE and s["accuracy"]>=TARGET:return t
    return None

def week_ci(rows,threshold):
    groups=defaultdict(list)
    for r in rows:
        if threshold is None or max(r["base"])>=threshold:
            groups[date.fromisoformat(r["date"]).strftime("%G-W%V")].append(int(max(range(3),key=lambda i:r["base"][i])==r["y"]))
    if len(groups)<12:return None
    blocks=list(groups.values());rng=random.Random(20261125);values=[]
    for _ in range(2000):
        a=[v for b in rng.choices(blocks,k=len(blocks)) for v in b]
        values.append(sum(a)/len(a))
    values.sort()
    return [values[50],values[1949]]

def evaluate(rows):
    seen=set();clean=[]
    for r in rows:
        k=(r["league"],*e.key(r));date.fromisoformat(r["date"])
        if k in seen or type(r["y"]) is not int or r["y"] not in (0,1,2):raise ValueError("INVALID_CASE")
        seen.add(k)
        clean.append({**r,"base":e.blend({k:e.vec(v) for k,v in r["p"].items()},WEIGHTS)})
    dev=[r for r in clean if r["date"]<CUT];test=[r for r in clean if r["date"]>=CUT]
    if len(dev)<100 or len(test)<100:raise ValueError("INSUFFICIENT_COHORT")
    threshold=select(dev)
    all_cases=summary(test)
    selected=summary(test,threshold) if threshold is not None else None
    ci=week_ci(test,threshold) if threshold is not None else None
    return {"schema":"v6-3-historical-70-percent-target-v1","target":TARGET,"cutoff":CUT,
        "development_n":len(dev),"assessment_n":len(test),"threshold":threshold,
        "full_assessment":all_cases,"full_assessment_week_ci":week_ci(test,None),
        "selected_development":summary(dev,threshold) if threshold is not None else None,
        "selected_assessment":selected,"selected_week_ci":ci,
        "full_point_target_met":all_cases["accuracy"]>=TARGET,
        "selected_point_target_met":bool(selected and selected["n"]>=MIN_ASSESSMENT and selected["coverage"]>=MIN_COVERAGE and selected["accuracy"]>=TARGET),
        "selected_conservative_target_met":bool(selected and selected["n"]>=MIN_ASSESSMENT and selected["coverage"]>=MIN_COVERAGE and ci and ci[0]>=TARGET),
        "diagnostic_thresholds_not_for_selection":[{"threshold":t,"development":summary(dev,t),"assessment":summary(test,t)} for t in THRESHOLDS],
        "assessment_previously_inspected":True,"prospective_validation":False,"automatic_promotion":False,
        "production_recommendations":"DISABLED","status":"HOLD"}

def main():
    p=argparse.ArgumentParser();p.add_argument("--input-dir",required=True);p.add_argument("--output",required=True);a=p.parse_args()
    from ops import v5_joint_poisson as joint,v5_dynamic_elo as elo,v5_ml_benchmark as ml
    rows=[]
    for league in ("en.1","de.1","fr.1"):
        def read(season):
            f=Path(a.input_dir)/f"{season}-{league}.json"
            if not 0<f.stat().st_size<=500000:raise ValueError("ARCHIVE_SIZE")
            return json.loads(f.read_text())
        r,_=e.league_cases(league,read("2024-25"),read("2025-26"),joint,elo,ml);rows+=r
    out=evaluate(rows)
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
