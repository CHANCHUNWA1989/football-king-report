"""V10.1 exact same-fixture bridge to pinned #644 ML classifiers; research only."""
import argparse
from collections import defaultdict
from datetime import date
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from ops import v10_super_core_research as core
from ops.v9_fixed_history_benchmark import load

ML_BLOB="993223d420f791bc890f10114241e35dd609cd0e"
ML_NAMES=("logistic","lightgbm","catboost","xgboost")
DEV=(2022,2023,2024)
TEST=2025
GRID=(0.,.25,.5,.75,1.)
FUSION=("ml_equal","fusion_fixed","fusion_adaptive")
ALL=core.MODELS+ML_NAMES+FUSION
def pinned_ml(path):
    raw=Path(path).read_bytes()
    if hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\x00"+raw).hexdigest()!=ML_BLOB:raise ValueError("ML_BLOB")
    spec=importlib.util.spec_from_file_location("pinned_v5_ml_benchmark",path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    if tuple(mod.BACKENDS)!=ML_NAMES:raise ValueError("BACKENDS")
    return mod
def document(rows):
    return {"matches":[{"date":d.isoformat(),"team1":h,"team2":a,"score":[x,y]} for d,h,a,x,y in rows]}
def case_key(r):
    return (date.fromisoformat(r["date"]),r["home"],r["away"])
def index_features(rows):
    out={}
    for r in rows:
        key=case_key(r)
        if key in out or type(r["y"]) is not int or r["y"] not in (0,1,2):raise ValueError("ML_CASE")
        out[key]=r
    return out
def vector(p):
    if len(p)!=3 or any(not math.isfinite(x) or not 0<=x<=1 for x in p) or abs(sum(p)-1)>1e-5:raise ValueError("ML_PROBABILITY")
    return core.normalize(p)
def match_predictions(rows,features,predictions):
    idx=index_features(features)
    keyed={}
    for i,r in enumerate(features):
        keyed[case_key(r)]={m:vector(predictions[m][i]) for m in ML_NAMES}
    base={(r["day"],r["h"],r["a"]):r for r in rows}
    if len(base)!=len(rows) or not set(idx)<=set(base):raise ValueError("COHORT")
    out=[]
    for key,r in base.items():
        z=idx.get(key)
        if z is not None and z["y"]!=r["y"]:raise ValueError("OUTCOME_CONFLICT")
        out.append({**r,"ml":keyed.get(key)})
    return out
def fold(data,league,year,rows,ml):
    test=data[year,league];cut=min(r[0] for r in test)
    train=[]
    for (sy,k),matches in sorted(data.items()):
        if k==league and sy<year and matches and max(r[0] for r in matches)<cut:
            train.extend(ml.features(document(matches)))
    if len(train)<200 or {r["y"] for r in train}!={0,1,2} or any(date.fromisoformat(r["date"])>=cut for r in train):raise ValueError("TRAIN_CLOCK")
    features=ml.features(document(test));predictions={}
    if not features:raise ValueError("NO_FEATURES")
    for m in ML_NAMES:
        model=ml.classifier(m)
        model.fit([r["x"] for r in train],[r["y"] for r in train])
        if list(model.classes_)!=[0,1,2]:raise ValueError("CLASS_ORDER")
        p=model.predict_proba([r["x"] for r in features])
        if len(p)!=len(features):raise ValueError("PREDICTION_COUNT")
        predictions[m]=[[float(x) for x in v] for v in p]
    return match_predictions(rows,features,predictions),{"league":league,"year":year,"training_n":len(train),"assessment_n":len(rows),"ml_available":len(features)}
def ml_avg(r):
    return core.normalize(tuple(sum(r["ml"][m][k] for m in ML_NAMES)/4 for k in range(3)))
def blend(r,w):
    p=r["p"]["dynamic_poisson"]
    if r["ml"] is None:return p
    return vector(tuple((1-w)*a+w*b for a,b in zip(p,ml_avg(r))))
def fit(rows,anchor):
    if any(r["year"] not in DEV for r in rows):raise ValueError("FUSION_TRAIN_SCOPE")
    known=[r for r in rows if r["ml"] is not None]
    if len(known)<200:return anchor
    return min(GRID,key=lambda w:(sum(-math.log(max(blend(r,w)[r["y"]],1e-15)) for r in known)/len(known)+.02*(w-anchor)**2,abs(w-anchor),w))
def evaluate(rows,receipts):
    keys=set()
    for r in rows:
        k=(r["year"],r["league"],r["day"],r["h"],r["a"])
        if k in keys or r["year"] not in (*DEV,TEST):raise ValueError("DUPLICATE_OR_SCOPE")
        keys.add(k)
    dev=[r for r in rows if r["year"] in DEV];test=[r for r in rows if r["year"]==TEST]
    if not dev or not test:raise ValueError("EMPTY")
    pooled=fit(dev,.5)
    weights={k:(pooled+fit([r for r in dev if r["league"]==k],pooled))/2 for k in sorted({r["league"] for r in test})}
    out=[]
    for r in test:
        p=dict(r["p"])
        p["fusion_fixed"]=blend(r,.5);p["fusion_adaptive"]=blend(r,weights[r["league"]])
        if r["ml"] is not None:p.update(r["ml"],ml_equal=ml_avg(r))
        out.append({**r,"p":p})
    common=[r for r in out if r["ml"] is not None]
    full=core.MODELS+("fusion_fixed","fusion_adaptive")
    scores=lambda a,models:{m:core.score(a,m) for m in models}
    return {"schema":"v10-1-ml-core-bridge-research-v1","development_n":len(dev),"assessment_n":len(out),
      "ml_available":len(common),"fallback_n":len(out)-len(common),"coverage":len(common)/len(out),
      "full_denominator_scores":scores(out,full),"common_fixture_scores":scores(common,ALL),
      "per_league":{k:scores([r for r in out if r["league"]==k],full) for k in weights},
      "pooled_ml_weight":pooled,"league_weights":weights,"fold_receipts":receipts,
      "paired_fusion_vs_dynamic":core.paired_blocks(out,"fusion_adaptive"),
      "ml_module_blob":ML_BLOB,"assessment_previously_inspected":True,"independent_assessment_count":0,
      "verified_forward_sample_credit":0,"automatic_promotion":False,"production_recommendations":"DISABLED","status":"HOLD"}
def build(data,ml):
    groups=defaultdict(dict)
    for (year,league),test in sorted(data.items()):
        train=data.get((year-1,league))
        if train is not None and len(train)>=100 and test:groups[year][league]=core.raw_rows(train,test)
    report,rows=core.evaluate(groups,return_rows=True)
    if len(rows)!=27835:raise ValueError("CORE_COHORT")
    out=[];receipts=[]
    for year in (*DEV,TEST):
        for league in sorted(groups[year]):
            subset=[r for r in rows if r["year"]==year and r["league"]==league]
            results,receipt=fold(data,league,year,subset,ml);out.extend(results);receipts.append(receipt)
    result=evaluate(out,receipts)
    if result["assessment_n"]!=2362 or result["development_n"]!=7146:raise ValueError("COHORT_COUNT")
    return result
def selftest():
    p={m:(.6,.2,.2) for m in core.MODELS}
    row={"day":date(2025,8,1),"h":"A","a":"B","y":0,"p":p,"year":2025,"league":"L"}
    feat={"date":"2025-08-01","home":"A","away":"B","y":0}
    preds={m:[(.7,.2,.1)] for m in ML_NAMES}
    a=match_predictions([row],[feat],preds)[0]
    assert blend(a,0)==p["dynamic_poisson"] and abs(blend(a,1)[0]-.7)<1e-12
    missing=match_predictions([row],[],{m:[] for m in ML_NAMES})[0]
    assert blend(missing,1)==p["dynamic_poisson"]
    try:match_predictions([row],[dict(feat,y=1)],preds)
    except ValueError:pass
    else:raise AssertionError("OUTCOME_CONFLICT")
    try:fit([a],.5)
    except ValueError:pass
    else:raise AssertionError("ASSESSMENT_LEAKAGE")
    dev=[{**a,"year":2024,"day":date(2024,8,1)}]
    r=evaluate(dev+[a],[])
    assert r["assessment_n"]==1 and r["ml_available"]==1 and r["status"]=="HOLD"
    r=evaluate(dev+[missing],[])
    assert r["fallback_n"]==1 and r["full_denominator_scores"]["fusion_adaptive"]==r["full_denominator_scores"]["dynamic_poisson"]
    return 6
if __name__=="__main__":
    p=argparse.ArgumentParser()
    for k in ("root","manifest","ml-module","output"):p.add_argument("--"+k,required=True)
    a=p.parse_args();checks=selftest()
    result=build(load(a.root,json.loads(Path(a.manifest).read_text())),pinned_ml(a.ml_module))
    with Path(a.output).open("x",encoding="utf-8") as f:json.dump(result,f,allow_nan=False,sort_keys=True)
    print(json.dumps({"synthetic_checks":checks,**{k:v for k,v in result.items() if k not in ("per_league","fold_receipts")}},allow_nan=False,sort_keys=True))
