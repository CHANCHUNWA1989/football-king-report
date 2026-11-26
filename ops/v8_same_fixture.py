"""V8.1 same-fixture comparison against the full seven-model baseline.
Fixed 50/50 challenger, no selection on the assessment, no promotion.
"""
import argparse
from collections import defaultdict
from datetime import date
import json
from pathlib import Path
import random
from ops import v5_joint_poisson as joint,v5_dynamic_elo as elo,v5_ml_benchmark as ml,v5_ensemble_competition as e
from ops import v8_multiseason as v8
from ops.v6_forward_bundle import decode,WEIGHTS

def document(rows):
    return {"matches":[{"date":d.isoformat(),"team1":h,"team2":a,"score":[x,y]} for d,h,a,x,y in rows]}

def paired(v8_rows,ensemble_rows):
    def index(rows):
        out={}
        for r in rows:
            k=(r["league"],*e.key(r))
            if k in out or type(r["y"]) is not int or r["y"] not in (0,1,2):raise ValueError("DUPLICATE_OR_INVALID_CASE")
            date.fromisoformat(r["date"]);out[k]=r
        return out
    a,b=index(v8_rows),index(ensemble_rows)
    if not set(b)<=set(a):raise ValueError("ENSEMBLE_FIXTURE_NOT_IN_V8")
    out=[]
    for k in sorted(b):
        r,s=a[k],b[k]
        if r["y"]!=s["y"]:raise ValueError("RESULT_CONFLICT")
        p=e.blend({n:e.vec(v) for n,v in s["p"].items()},WEIGHTS)
        q=e.vec(r["candidate"])
        out.append({"league":k[0],"date":k[1],"home":k[2],"away":k[3],"y":r["y"],
            "ensemble":p,"v8":q,"hybrid":e.vec([(x+y)/2 for x,y in zip(p,q)])})
    return out

MODELS=("ensemble","v8","hybrid")
def ci(rows,model):
    blocks=defaultdict(list)
    for r in rows:
        blocks[date.fromisoformat(r["date"]).strftime("%G-W%V")].append(e.loss(r["ensemble"],r["y"])-e.loss(r[model],r["y"]))
    if len(blocks)<12:return None
    groups=list(blocks.values());rng=random.Random(20261125);values=[]
    for _ in range(1000):
        a=[v for b in rng.choices(groups,k=len(groups)) for v in b];values.append(sum(a)/len(a))
    values.sort();return [values[25],values[974]]

def metrics(rows):
    return {k:e.metrics(rows,lambda r:r[k]) for k in MODELS}

def compare(rows,total):
    if not rows or type(total) is not int or total<len(rows):raise ValueError("INVALID_COVERAGE")
    scores=metrics(rows)
    # Same selected fixtures for every model, threshold fixed before this comparison.
    # Independent per-model selection also reported with its own denominator.
    common=[r for r in rows if max(r["ensemble"])>=.50]
    individual={}
    for k in MODELS:
        a=[r for r in rows if max(r[k])>=.50]
        individual[k]={"n":len(a),"coverage_of_all_finished":len(a)/total,"metrics":e.metrics(a,lambda r:r[k])}
    intervals={k:ci(rows,k) for k in ("v8","hybrid")}
    return {"all_finished":total,"common_n":len(rows),"coverage":len(rows)/total,"same_fixture_metrics":scores,
        "same_ensemble_selected_cohort":{"n":len(common),"coverage_of_all_finished":len(common)/total,"metrics":metrics(common)},
        "individual_fixed_threshold_50":individual,"paired_week_ci_ensemble_minus_candidate":intervals,
        "proper_score_gates":{k:bool(scores[k]["log_loss"]<scores["ensemble"]["log_loss"] and scores[k]["brier"]<scores["ensemble"]["brier"] and intervals[k] and intervals[k][0]>0) for k in intervals}}

def build(data):
    all_rows=[];scope=[];total=0
    for league in v8.LEAGUES:
        tr=data.get(("2024-25",league));te=data.get(("2025-26",league))
        if te is not None:total+=len(te)
        if tr is None or te is None or len(tr)<100 or not te:
            scope.append({"league":league,"status":"HOLD","reason":"MISSING_SCOPE"});continue
        a=v8.replay(tr,te,league,"2025-26")
        b,_=e.league_cases(league,document(tr),document(te),joint,elo,ml)
        rows=paired(a,b)
        if not rows:
            scope.append({"league":league,"status":"HOLD","reason":"NO_COMMON_FIXTURES","all_finished":len(te)});continue
        scope.append({"league":league,**compare(rows,len(te))})
        all_rows+=rows
    return {"schema":"v8-1-same-fixture-competition-v1","season":"2025-26","source_commit":v8.PIN,
        "pooled":compare(all_rows,total),"per_league":scope,"hybrid_weights":{"v8":.5,"seven_model_ensemble":.5},
        "assessment_previously_inspected":True,"partial_archives_used_as_available":True,
        "prospective_validation":False,"market_comparison_available":False,"result_source_independently_verified":False,
        "verified_forward_sample_credit":0,"automatic_promotion":False,"production_recommendations":"DISABLED","status":"HOLD"}

def main():
    p=argparse.ArgumentParser()
    for k in ("input-dir","manifest","output"):p.add_argument("--"+k,required=True)
    a=p.parse_args()
    data,_=v8.load(a.input_dir,decode(Path(a.manifest).read_bytes()))
    out=build(data)
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
