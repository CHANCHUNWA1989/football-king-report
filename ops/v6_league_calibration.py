"""V6.1 league-specific conservative calibration; exploratory only."""
import argparse
from collections import defaultdict
from datetime import date
import json
from pathlib import Path
import random
from ops import v5_ensemble_competition as e
from ops.v6_calibration_challenger import calibrate, WEIGHTS, CUT, TEMPS, SHIFTS

IDENTITY=(1.,0.,0.)
MIN_LEAGUE=60
def fit(rows):
    if any(r["date"]>=CUT for r in rows):raise ValueError("ASSESSMENT_LEAKAGE")
    if len(rows)<MIN_LEAGUE or set(r["y"] for r in rows)!={0,1,2}:return IDENTITY
    # Conservative shrinkage toward no calibration; all choices fixed before fit.
    candidates=[]
    for t in TEMPS:
        for h in SHIFTS:
            for d in SHIFTS:
                penalty=(.02+5/len(rows))*((t-1)**2+h*h+d*d)
                loss=sum(e.loss(calibrate(r["base"],t,h,d),r["y"]) for r in rows)/len(rows)
                candidates.append((loss+penalty,(t-1)**2+h*h+d*d,t,h,d))
    return min(candidates)[2:]

def paired_ci(rows,fn):
    groups=defaultdict(list)
    for r in rows:
        groups[date.fromisoformat(r["date"]).strftime("%G-W%V")].append(e.loss(r["base"],r["y"])-e.loss(fn(r),r["y"]))
    if len(groups)<12:return None
    blocks=list(groups.values());rng=random.Random(20261125);draws=[]
    for _ in range(1000):
        a=[v for b in rng.choices(blocks,k=len(blocks)) for v in b];draws.append(sum(a)/len(a))
    draws.sort()
    return [draws[25],draws[974]]

def evaluate(rows):
    seen=set();clean=[]
    for r in rows:
        k=(r["league"],*e.key(r));date.fromisoformat(r["date"])
        if k in seen or type(r["y"]) is not int or r["y"] not in (0,1,2):raise ValueError("INVALID_CASE")
        seen.add(k);clean.append({**r,"base":e.blend({k:e.vec(v) for k,v in r["p"].items()},WEIGHTS)})
    dev=[r for r in clean if r["date"]<CUT];test=[r for r in clean if r["date"]>=CUT]
    if len(dev)<100 or len(test)<100:raise ValueError("INSUFFICIENT_COHORT")
    scopes=sorted({r["league"] for r in clean})
    params={k:fit([r for r in dev if r["league"]==k]) for k in scopes}
    fn=lambda r:calibrate(r["base"],*params[r["league"]])
    base=lambda r:r["base"]
    b,c=e.metrics(test,base),e.metrics(test,fn);ci=paired_ci(test,fn)
    per={}
    for k in scopes:
        a=[r for r in test if r["league"]==k]
        d=[r for r in dev if r["league"]==k]
        per[k]={"development_n":len(d),"params":list(params[k]),"baseline":e.metrics(a,base),"candidate":e.metrics(a,fn)}
    return {"schema":"v6-1-league-calibration-research-v1","cutoff":CUT,"development_n":len(dev),"assessment_n":len(test),
        "assessment_baseline":b,"assessment_candidate":c,"per_league":per,"paired_week_block_ci":ci,
        "historical_gate":bool(c["log_loss"]<b["log_loss"] and c["brier"]<b["brier"] and ci is not None and ci[0]>0),
        "assessment_previously_inspected":True,"prospective_validation":False,"market_comparison_available":False,
        "automatic_promotion":False,"production_recommendations":"DISABLED","status":"HOLD"}

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
