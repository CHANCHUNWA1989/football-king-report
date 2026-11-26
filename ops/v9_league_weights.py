"""V9.5 conservative league-specific ensemble/rolling-model blend.
Fixed development folds; assessment previously inspected; no promotion.
"""
import argparse,json,random
from collections import defaultdict
from datetime import date
from pathlib import Path
from ops import v8_multiseason as v,v8_same_fixture as s
from ops import v5_ensemble_competition as e,v5_joint_poisson as joint,v5_dynamic_elo as elo,v5_ml_benchmark as ml
from ops.v6_forward_bundle import decode
from ops.v9_historical_elo import adapter

DEV=("2022-23","2023-24","2024-25")
TEST="2025-26"
GRID=(0.,.25,.5,.75,1.)
MIN_DEV=200
def blend(r,w):
    if not 0<=w<=1:raise ValueError("WEIGHT")
    return e.vec([(1-w)*a+w*b for a,b in zip(e.vec(r["ensemble"]),e.vec(r["v8"]))])
def choose(rows,anchor=.5):
    if len(rows)<MIN_DEV or any(r["season"] not in DEV or r["date"]>="2025-07-01" for r in rows):raise ValueError("DEVELOPMENT")
    if {r["y"] for r in rows}!={0,1,2}:raise ValueError("DEVELOPMENT_CLASSES")
    def obj(w):
        distance=(w-anchor)**2
        return (sum(e.loss(blend(r,w),r["y"]) for r in rows)/len(rows)+.02*distance,distance,w)
    return min(GRID,key=obj)
def select(dev):
    pooled=choose(dev)
    weights={}
    for league in v.LEAGUES:
        rows=[r for r in dev if r["league"]==league]
        local=choose(rows,pooled) if len(rows)>=MIN_DEV and {r["y"] for r in rows}=={0,1,2} else pooled
        # Shrink league-specific choice halfway toward pooled, not a new fitted parameter.
        weights[league]={"development_n":len(rows),"local_grid_weight":local,"final_v8_weight":(local+pooled)/2}
    return pooled,weights
def ci(rows):
    groups=defaultdict(list)
    for r in rows:
        groups[date.fromisoformat(r["date"]).strftime("%G-W%V")].append(e.loss(r["hybrid"],r["y"])-e.loss(r["candidate"],r["y"]))
    if len(groups)<12:return None
    blocks=list(groups.values());rng=random.Random(20261126);vals=[]
    for _ in range(1000):
        z=[x for b in rng.choices(blocks,k=len(blocks)) for x in b];vals.append(sum(z)/len(z))
    vals.sort();return [vals[25],vals[974]]
def compare(rows,total):
    if not rows or len(rows)>total:raise ValueError("COVERAGE")
    keys=("ensemble","v8","hybrid","candidate")
    def scores(a):return {k:e.metrics(a,lambda r:r[k]) for k in keys}
    m=scores(rows);interval=ci(rows)
    common=[r for r in rows if max(r["hybrid"])>=.5]
    return {"all_finished":total,"common_n":len(rows),"coverage":len(rows)/total,"same_fixture_metrics":m,
        "same_hybrid_selected":{"n":len(common),"metrics":scores(common)},
        "individual_threshold_50":{k:{"n":len(a),"coverage_of_all_finished":len(a)/total,"metrics":e.metrics(a,lambda r:r[k])} for k in keys for a in [[r for r in rows if max(r[k])>=.5]]},
        "paired_week_ci_hybrid_minus_candidate":interval,
        "historical_proper_score_gate":bool(interval and interval[0]>0 and all(m["candidate"][k]<m["hybrid"][k] for k in ("log_loss","brier")))}
def evaluate(rows,totals):
    seen=set();dev=[];test=[]
    for r in rows:
        k=(r["league"],r["season"],*e.key(r))
        if k in seen or r["league"] not in v.LEAGUES or type(r["y"]) is not int or r["y"] not in (0,1,2):raise ValueError("CASE")
        seen.add(k);date.fromisoformat(r["date"])
        if r["season"] in DEV:dev.append(r)
        elif r["season"]==TEST:
            if r["date"]<"2025-07-01":raise ValueError("ASSESSMENT_CLOCK")
            test.append(r)
    pooled,weights=select(dev)
    out=[{**r,"candidate":blend(r,weights[r["league"]]["final_v8_weight"])} for r in test]
    return {"schema":"v9-5-league-adaptive-ensemble-research-v1","development_n":len(dev),"development_seasons":DEV,
        "pooled_v8_weight":pooled,"league_weights":weights,"assessment_season":TEST,
        "pooled":compare(out,sum(totals.values())),
        "per_league":{k:compare([r for r in out if r["league"]==k],totals[k]) for k in v.LEAGUES},
        "weight_grid":GRID,"baseline_definition":"V8.1 fixed half seven-model ensemble and half V8 dynamic DC",
        "assessment_previously_inspected":True,"partial_archives_used_as_available":True,"prospective_validation":False,
        "verified_forward_sample_credit":0,"production_recommendations":"DISABLED","automatic_promotion":False,"status":"HOLD"}
def build(data):
    rows=[];totals={}
    for league in v.LEAGUES:
        for old,new in zip(v.SEASONS,v.SEASONS[1:]):
            tr,te=data[old,league],data[new,league]
            if new==TEST:totals[league]=len(te)
            a=v.replay(tr,te,league,new)
            b,_=e.league_cases(league,s.document(tr),s.document(te),joint,adapter(new),ml)
            cases=s.paired(a,b)
            if not cases:raise ValueError("EMPTY_SCOPE")
            rows.extend({**r,"season":new} for r in cases)
    return evaluate(rows,totals)
def main():
    p=argparse.ArgumentParser()
    for k in ("input-dir","manifest","output"):p.add_argument("--"+k,required=True)
    a=p.parse_args();data,_=v.load(a.input_dir,decode(Path(a.manifest).read_bytes()))
    out=build(data)
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
