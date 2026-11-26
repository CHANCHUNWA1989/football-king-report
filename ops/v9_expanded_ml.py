"""V9.7 expanding historical ML vs single-season ML and DC on identical cases."""
import argparse,json
from pathlib import Path
from ops import v9_history_expansion as hx,v8_multiseason as v,v8_same_fixture as s
from ops import v5_ml_benchmark as ml,v5_ensemble_competition as e
from ops.v6_forward_bundle import decode

TEST="2025-26"
def training_partition(data,league):
    test=data[TEST,league]
    cutoff=min(r[0] for r in test)
    prior=[];excluded=[]
    for (season,k),rows in sorted(data.items()):
        if k!=league or season>=TEST:continue
        if not rows or max(r[0] for r in rows)>=cutoff:
            excluded.append(season);continue
        f=ml.features(s.document(rows))
        prior.extend({**r,"season":season} for r in f)
    if any(r["date"]>=cutoff.isoformat() for r in prior):raise ValueError("TRAIN_LEAKAGE")
    recent=[r for r in prior if r["season"]=="2024-25"]
    if len(recent)<100 or len(prior)<200 or {r["y"] for r in recent}!={0,1,2} or {r["y"] for r in prior}!={0,1,2}:raise ValueError("INSUFFICIENT_TRAIN")
    return prior,recent,excluded
def predict(train,test):
    result={}
    for name in ml.BACKENDS:
        model=ml.classifier(name)
        model.fit([r["x"] for r in train],[r["y"] for r in train])
        if list(model.classes_)!=[0,1,2]:raise ValueError("CLASS_ORDER")
        values=model.predict_proba([r["x"] for r in test])
        if len(values)!=len(test):raise ValueError("PREDICTION_LENGTH")
        result[name]=[e.vec([float(v) for v in p]) for p in values]
    return result
def average(p,i):
    return e.vec([sum(p[k][i][j] for k in ml.BACKENDS)/len(ml.BACKENDS) for j in range(3)])
def build(data):
    all_rows=[];scopes={};all_finished=0
    for league in v.LEAGUES:
        tr,te=data["2024-25",league],data[TEST,league]
        all_finished+=len(te)
        past,recent,excluded=training_partition(data,league)
        test=ml.features(s.document(te))
        if not test:raise ValueError("NO_TEST")
        base={e.key(r):r for r in v.replay(tr,te,league,TEST)}
        a,b=predict(recent,test),predict(past,test)
        rows=[]
        for i,r in enumerate(test):
            k=e.key(r)
            if k not in base or base[k]["y"]!=r["y"]:raise ValueError("COHORT_CONFLICT")
            rows.append({"date":r["date"],"y":r["y"],"dc":base[k]["candidate"],
                "recent_ml":average(a,i),"expanded_ml":average(b,i),
                "expanded_backends":{n:b[n][i] for n in ml.BACKENDS}})
        scopes[league]={"raw_assessment":len(te),"train_recent":len(recent),"train_expanded":len(past),
            "train_seasons":sorted({r["season"] for r in past}),"excluded_training_seasons":excluded,"metrics":scores(rows)}
        all_rows.extend(rows)
    return {"schema":"v9-7-expanded-ml-research-v1","all_finished_assessment":all_finished,"common_assessment_n":len(all_rows),
        "coverage":len(all_rows)/all_finished,"per_league":scopes,"same_fixture":scores(all_rows),
        "fixed_equal_ml_weights":True,"training_scope":"all eligible prior seasons vs previous season only; each season features reset",
        "assessment_previously_inspected":True,"historical_results_independently_verified":False,
        "prospective_validation":False,"verified_forward_sample_credit":0,"production_recommendations":"DISABLED","automatic_promotion":False,"status":"HOLD"}
def scores(rows):
    return {**{k:e.metrics(rows,lambda r:r[k]) for k in ("dc","recent_ml","expanded_ml")},
        "expanded_backends":{k:e.metrics(rows,lambda r:r["expanded_backends"][k]) for k in ml.BACKENDS}}
def main():
    p=argparse.ArgumentParser()
    for k in ("input-dir","manifest","base-dir","base-manifest","output"):p.add_argument("--"+k,required=True)
    a=p.parse_args();old,_=v.load(a.base_dir,decode(Path(a.base_manifest).read_bytes()));new,_=hx.load(a.input_dir,decode(Path(a.manifest).read_bytes()))
    out=build(hx.combine(old,new))
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
