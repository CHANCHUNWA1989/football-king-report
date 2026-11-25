"""V10 causal domestic fusion research, full-denominator fallback, no production promotion."""
import argparse,json,random
from collections import defaultdict
from datetime import date
from pathlib import Path
from ops import v8_multiseason as v,v8_same_fixture as s,v9_history_expansion as hx,v9_expanded_ml as x
from ops import v5_ml_benchmark as ml,v5_ensemble_competition as e
from ops.v6_forward_bundle import decode
DEV=("2022-23","2023-24","2024-25")
TEST="2025-26"
GRID=(0.,.25,.5,.75,1.)
def blend(r,w):
    if not 0<=w<=1:raise ValueError("WEIGHT")
    p=e.vec(r["dc"])
    if r["ml"] is None:return p
    q=e.vec(r["ml"])
    return e.vec([(1-w)*a+w*b for a,b in zip(p,q)])
def fit(rows,anchor):
    if len(rows)<200 or any(r["season"] not in DEV or r["date"]>="2025-07-01" for r in rows):raise ValueError("DEVELOPMENT_SCOPE")
    known=[r for r in rows if r["ml"] is not None]
    if len(known)<200 or {r["y"] for r in known}!={0,1,2}:raise ValueError("DEVELOPMENT_FEATURES")
    def objective(w):
        penalty=(w-anchor)**2
        return (sum(e.loss(blend(r,w),r["y"]) for r in known)/len(known)+.02*penalty,penalty,w)
    return min(GRID,key=objective)
def fold(data,league,season):
    prev=v.SEASONS[v.SEASONS.index(season)-1]
    te=data[season,league];tr=data[prev,league];cut=min(r[0] for r in te)
    train=[]
    for (sy,k),rows in sorted(data.items()):
        if k==league and sy<season and rows and max(r[0] for r in rows)<cut:
            train.extend(ml.features(s.document(rows)))
    if len(train)<200 or any(r["date"]>=cut.isoformat() for r in train):raise ValueError("TRAIN_SCOPE")
    test=ml.features(s.document(te));probs=x.predict(train,test)
    index={e.key(r):(r["y"],x.average(probs,i)) for i,r in enumerate(test)}
    if len(index)!=len(test):raise ValueError("DUPLICATE_FEATURE")
    base=v.replay(tr,te,league,season)
    if len(base)!=len(te) or not set(index)<={e.key(r) for r in base}:raise ValueError("COHORT")
    out=[]
    for r in base:
        z=index.get(e.key(r))
        if z is not None and z[0]!=r["y"]:raise ValueError("OUTCOME_CONFLICT")
        out.append({**r,"dc":r["candidate"],"ml":z[1] if z else None})
    return out,{"league":league,"season":season,"training_n":len(train),"assessment_n":len(out),"ml_available":len(index)}
def interval(rows):
    groups=defaultdict(list)
    for r in rows:groups[date.fromisoformat(r["date"]).strftime("%G-W%V")].append(e.loss(r["dc"],r["y"])-e.loss(r["fusion"],r["y"]))
    if len(groups)<12:return None
    blocks=list(groups.values());rng=random.Random(20261126);out=[]
    for _ in range(1000):
        z=[v for b in rng.choices(blocks,k=len(blocks)) for v in b];out.append(sum(z)/len(z))
    out.sort();return [out[25],out[974]]
def compare(rows):
    if not rows:raise ValueError("EMPTY")
    known=[r for r in rows if r["ml"] is not None]
    def scores(a):return {k:e.metrics(a,lambda r:r[k]) for k in ("dc","half","fusion")}
    a=scores(rows);ci=interval(rows)
    return {"n":len(rows),"ml_available":len(known),"fallback_n":len(rows)-len(known),
        "all_same_fixture":a,"ml_available_same_fixture":{**scores(known),"pure_ml":e.metrics(known,lambda r:r["ml"])},
        "paired_week_ci_dc_minus_fusion":ci,"historical_proper_score_gate":bool(ci and ci[0]>0 and all(a["fusion"][k]<a["dc"][k] for k in ("log_loss","brier")))}
def evaluate(rows,receipts):
    seen=set();dev=[];test=[]
    for r in rows:
        k=(r["league"],r["season"],*e.key(r))
        if k in seen or r["league"] not in v.LEAGUES or type(r["y"]) is not int or r["y"] not in (0,1,2):raise ValueError("CASE")
        seen.add(k);date.fromisoformat(r["date"])
        if r["season"] in DEV:dev.append(r)
        elif r["season"]==TEST:
            if r["date"]<"2025-07-01":raise ValueError("ASSESSMENT_CLOCK")
            test.append(r)
        else:raise ValueError("SEASON")
    pooled=fit(dev,.5);weights={}
    for league in v.LEAGUES:
        local=fit([r for r in dev if r["league"]==league],pooled)
        weights[league]=(local+pooled)/2
    result=[{**r,"half":blend(r,.5),"fusion":blend(r,weights[r["league"]])} for r in test]
    return {"schema":"v10-domestic-fusion-research-v1","development_n":len(dev),"assessment_n":len(test),
        "pooled_ml_weight":pooled,"league_ml_weights":weights,"fold_receipts":receipts,
        "pooled":compare(result),"per_league":{k:compare([r for r in result if r["league"]==k]) for k in v.LEAGUES},
        "baseline_definition":"V8 dynamic DC; expanded ML equal-weight four backends; no seven-model baseline claim",
        "assessment_previously_inspected":True,"prospective_validation":False,"verified_forward_sample_credit":0,
        "production_recommendations":"DISABLED","automatic_promotion":False,"status":"HOLD"}
def main():
    p=argparse.ArgumentParser()
    for k in ("input-dir","manifest","base-dir","base-manifest","output"):p.add_argument("--"+k,required=True)
    a=p.parse_args();old,_=v.load(a.base_dir,decode(Path(a.base_manifest).read_bytes()));new,_=hx.load(a.input_dir,decode(Path(a.manifest).read_bytes()))
    data=hx.combine(old,new);rows=[];receipts=[]
    for league in v.LEAGUES:
        for season in (*DEV,TEST):
            r,receipt=fold(data,league,season);rows+=r;receipts.append(receipt)
    out=evaluate(rows,receipts)
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
