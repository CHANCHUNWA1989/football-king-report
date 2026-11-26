"""Frozen chronological calibration challenger; no deployment or market claim."""
import argparse
from collections import defaultdict
from datetime import date
import json
import math
from pathlib import Path
import random
from ops import v5_ensemble_competition as e

WEIGHTS={k:.5 if k=="joint_poisson" else 1/12 for k in e.NAMES}
CUT="2026-01-01"
# Fixed small grid and regularization; assessment never used for fitting.
TEMPS=(.85,1.,1.15,1.3,1.5)
SHIFTS=(-.15,0.,.15)
def calibrate(p,t,h,d):
    if t not in TEMPS or h not in SHIFTS or d not in SHIFTS:raise ValueError("UNKNOWN_PARAMETER")
    p=e.vec(p)
    z=[math.log(max(v,1e-15))/t+b for v,b in zip(p,(h,d,0.))]
    z=[math.exp(v-max(z)) for v in z]
    return e.vec([v/sum(z) for v in z])

def fit(rows):
    if len(rows)<100 or len({r["y"] for r in rows})!=3:raise ValueError("INSUFFICIENT_DEVELOPMENT")
    if any(r["date"]>=CUT for r in rows):raise ValueError("ASSESSMENT_LEAKAGE")
    candidates=[]
    for t in TEMPS:
        for h in SHIFTS:
            for d in SHIFTS:
                loss=sum(e.loss(calibrate(r["base"],t,h,d),r["y"]) for r in rows)/len(rows)
                penalty=.02*((t-1)**2+h*h+d*d)
                candidates.append((loss+penalty,(t-1)**2+h*h+d*d,t,h,d))
    return min(candidates)[2:]

def block_ci(rows,params):
    groups=defaultdict(list)
    for r in rows:
        week=date.fromisoformat(r["date"]).strftime("%G-W%V")
        groups[week].append(e.loss(r["base"],r["y"])-e.loss(calibrate(r["base"],*params),r["y"]))
    if len(groups)<12:return None
    blocks=list(groups.values());rng=random.Random(20261125);draws=[]
    for _ in range(1000):
        a=[v for b in rng.choices(blocks,k=len(blocks)) for v in b];draws.append(sum(a)/len(a))
    draws.sort()
    return [draws[25],draws[974]]

def reliability(rows,fn):
    bins=[]
    for i in range(3):
        for j in range(5):
            cases=[(fn(r)[i],int(r["y"]==i)) for r in rows if min(int(fn(r)[i]*5),4)==j]
            if cases:bins.append({"class":i,"bin":j,"n":len(cases),"mean_probability":sum(x for x,y in cases)/len(cases),"observed":sum(y for x,y in cases)/len(cases)})
    return bins

def evaluate(rows):
    seen=set();clean=[]
    for r in rows:
        k=(r["league"],*e.key(r))
        date.fromisoformat(r["date"])
        if k in seen or type(r["y"]) is not int or r["y"] not in (0,1,2):raise ValueError("INVALID_OR_DUPLICATE_CASE")
        seen.add(k)
        p={k:e.vec(v) for k,v in r["p"].items()}
        clean.append({**r,"base":e.blend(p,WEIGHTS)})
    dev=[r for r in clean if r["date"]<CUT];test=[r for r in clean if r["date"]>=CUT]
    if len(test)<100:raise ValueError("INSUFFICIENT_ASSESSMENT")
    par=fit(dev)
    base=lambda r:r["base"]
    cand=lambda r:calibrate(r["base"],*par)
    b=e.metrics(test,base);c=e.metrics(test,cand);ci=block_ci(test,par)
    return {"schema":"v6-chronological-calibration-challenger-v1","cutoff":CUT,"development_n":len(dev),"assessment_n":len(test),
        "params":{"temperature":par[0],"home_log_shift":par[1],"draw_log_shift":par[2]},
        "development_baseline":e.metrics(dev,base),"development_candidate":e.metrics(dev,cand),
        "assessment_baseline":b,"assessment_candidate":c,"paired_week_block_ci_baseline_minus_candidate":ci,
        "per_league":{k:{"baseline":e.metrics([r for r in test if r["league"]==k],base),"candidate":e.metrics([r for r in test if r["league"]==k],cand)} for k in sorted({r["league"] for r in test})},
        "baseline_reliability":reliability(test,base),"candidate_reliability":reliability(test,cand),
        "historical_proper_score_gate":bool(c["log_loss"]<b["log_loss"] and c["brier"]<b["brier"] and ci is not None and ci[0]>0),
        "assessment_previously_inspected":True,"prospective_validation":False,"market_comparison_available":False,
        "automatic_promotion":False,"production_recommendations":"DISABLED","status":"HOLD"}

def main():
    p=argparse.ArgumentParser()
    for k in ("input-dir","output"):p.add_argument("--"+k,required=True)
    a=p.parse_args()
    from ops import v5_joint_poisson as joint,v5_dynamic_elo as elo,v5_ml_benchmark as ml
    rows=[]
    for league in ("en.1","de.1","fr.1"):
        def read(season):
            f=Path(a.input_dir)/f"{season}-{league}.json"
            if not 0<f.stat().st_size<=500000:raise ValueError("ARCHIVE_SIZE")
            return json.loads(f.read_text())
        r,_=e.league_cases(league,read("2024-25"),read("2025-26"),joint,elo,ml)
        rows+=r
    out=evaluate(rows)
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in out.items() if not k.endswith("reliability")},allow_nan=False))
if __name__=="__main__":main()
