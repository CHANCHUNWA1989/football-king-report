"""V11 nonlinear stacked probability research and temporal uncertainty sets."""
import argparse,json,math,random
from collections import defaultdict
from datetime import date
from pathlib import Path
from ops import v10_fusion as f,v8_multiseason as v,v8_same_fixture as s,v9_history_expansion as hx,v9_expanded_ml as x
from ops import v5_ml_benchmark as ml,v5_ensemble_competition as e
from ops.v6_forward_bundle import decode
FIT=("2022-23","2023-24")
CAL="2024-25"
TEST="2025-26"
ALPHA=.1
def entropy(p):return -sum(z*math.log(max(z,1e-15)) for z in p)
def features(r):
    if r["ml"] is None:return None
    p=e.vec(r["dc"])
    q=e.vec(r["ml"])
    models=[p]+[e.vec(r["backends"][k]) for k in ml.BACKENDS]
    if any(abs(q[i]-sum(a[i] for a in models[1:])/4)>1e-8 for i in range(3)):raise ValueError("ML_MEAN_CONFLICT")
    z=[n for a in models for n in a]
    z += [entropy(a) for a in models]
    z += [max(a[i] for a in models)-min(a[i] for a in models) for i in range(3)]
    z += [sum(abs(a-b) for a,b in zip(p,q))/2, max(p),max(q)]
    z += [int(r["league"]==k) for k in v.LEAGUES]
    return z
def fold(data,league,season):
    prev=v.SEASONS[v.SEASONS.index(season)-1]
    tr,te=data[prev,league],data[season,league];cut=min(r[0] for r in te)
    train=[]
    for (sy,k),rows in sorted(data.items()):
        if k==league and sy<season and rows and max(r[0] for r in rows)<cut:
            train.extend(ml.features(s.document(rows)))
    if len(train)<200 or any(r["date"]>=cut.isoformat() for r in train):raise ValueError("TRAIN_SCOPE")
    test=ml.features(s.document(te));probs=x.predict(train,test)
    idx={e.key(r):(r["y"],x.average(probs,i),{k:probs[k][i] for k in ml.BACKENDS}) for i,r in enumerate(test)}
    base=v.replay(tr,te,league,season)
    if len(idx)!=len(test) or len(base)!=len(te) or not set(idx)<={e.key(r) for r in base}:raise ValueError("COHORT")
    out=[]
    for r in base:
        z=idx.get(e.key(r))
        if z is not None and z[0]!=r["y"]:raise ValueError("OUTCOME_CONFLICT")
        out.append({**r,"dc":r["candidate"],"ml":z[1] if z else None,"backends":z[2] if z else None})
    return out
def fit_stack(rows):
    if any(r["season"] not in FIT or r["date"]>="2024-07-01" for r in rows):raise ValueError("STACK_LEAKAGE")
    a=[r for r in rows if r["ml"] is not None]
    if len(a)<500 or {r["y"] for r in a}!={0,1,2}:raise ValueError("STACK_COHORT")
    from sklearn.ensemble import HistGradientBoostingClassifier
    from threadpoolctl import threadpool_limits
    model=HistGradientBoostingClassifier(max_iter=80,max_leaf_nodes=7,min_samples_leaf=100,l2_regularization=10.,learning_rate=.05,early_stopping=False,random_state=42)
    with threadpool_limits(limits=1):model.fit([features(r) for r in a],[r["y"] for r in a])
    if list(model.classes_)!=[0,1,2]:raise ValueError("CLASS_ORDER")
    return model
def predict(rows,model):
    from threadpoolctl import threadpool_limits
    a=[(i,r) for i,r in enumerate(rows) if r["ml"] is not None]
    out=[e.vec(r["dc"]) for r in rows]
    if a:
        with threadpool_limits(limits=1):p=model.predict_proba([features(r) for _,r in a])
        if len(p)!=len(a):raise ValueError("PREDICTION_LENGTH")
        for (i,r),q in zip(a,p):
            # Predeclared 50% shrink to the equal DC/ML anchor.
            out[i]=e.vec([(b+c)/2 for b,c in zip(f.blend(r,.5),e.vec([float(z) for z in q]))])
    return out
def quantile(rows):
    if len(rows)<100 or any(r["season"]!=CAL or not "2024-07-01"<=r["date"]<"2025-07-01" for r in rows):raise ValueError("CALIBRATION_SCOPE")
    a=sorted(1-e.vec(r["stack"])[r["y"]] for r in rows)
    rank=math.ceil((len(a)+1)*(1-ALPHA))
    return a[rank-1] if rank<=len(a) else 1.
def prediction_set(p,q):
    if not 0<=q<=1:raise ValueError("QUANTILE")
    p=e.vec(p)
    z=[i for i in range(3) if 1-p[i]<=q]
    return z or [max(range(3),key=lambda i:p[i])]
def sets(rows,q):
    if not rows:return None
    a=[(prediction_set(r["stack"],q),r["y"]) for r in rows]
    return {"n":len(a),"empirical_coverage":sum(y in z for z,y in a)/len(a),"mean_set_size":sum(len(z) for z,y in a)/len(a),
        "singleton_n":sum(len(z)==1 for z,y in a),"three_outcome_n":sum(len(z)==3 for z,y in a)}
def ci(rows):
    groups=defaultdict(list)
    for r in rows:groups[date.fromisoformat(r["date"]).strftime("%G-W%V")].append(e.loss(r["v10"],r["y"])-e.loss(r["stack"],r["y"]))
    if len(groups)<12:return None
    blocks=list(groups.values());rng=random.Random(20261126);out=[]
    for _ in range(1000):
        a=[x for b in rng.choices(blocks,k=len(blocks)) for x in b];out.append(sum(a)/len(a))
    out.sort();return [out[25],out[974]]
def compare(rows,q):
    m={k:e.metrics(rows,lambda r:r[k]) for k in ("dc","v10","stack")}
    i=ci(rows)
    return {"n":len(rows),"ml_available":sum(r["ml"] is not None for r in rows),"metrics":m,
        "uncertainty_sets":sets(rows,q),"paired_week_ci_v10_minus_stack":i,
        "historical_proper_score_gate":bool(i and i[0]>0 and all(m["stack"][k]<m["v10"][k] for k in ("log_loss","brier")))}
def evaluate(rows):
    seen=set()
    for r in rows:
        k=(r["league"],r["season"],*e.key(r))
        if k in seen or r["league"] not in v.LEAGUES or type(r["y"]) is not int or r["y"] not in (0,1,2):raise ValueError("CASE")
        seen.add(k);date.fromisoformat(r["date"])
        if r["season"] not in (*FIT,CAL,TEST):raise ValueError("SEASON")
    fit=[r for r in rows if r["season"] in FIT];cal=[r for r in rows if r["season"]==CAL];test=[r for r in rows if r["season"]==TEST]
    if len(test)!=2362 or any(r["date"]<"2025-07-01" for r in test):raise ValueError("ASSESSMENT")
    model=fit_stack(fit)
    cal=[{**r,"stack":p} for r,p in zip(cal,predict(cal,model))]
    q=quantile(cal)
    dev=fit+cal;pooled=f.fit(dev,.5)
    w={k:(f.fit([r for r in dev if r["league"]==k],pooled)+pooled)/2 for k in v.LEAGUES}
    test=[{**r,"stack":p,"v10":f.blend(r,w[r["league"]])} for r,p in zip(test,predict(test,model))]
    return {"schema":"v11-nonlinear-stack-research-v1","stack_training_n":len(fit),"stack_training_ml_available":sum(r["ml"] is not None for r in fit),
        "calibration_n":len(cal),"assessment_n":len(test),"target_set_coverage":1-ALPHA,"set_quantile":q,
        "v10_weights":w,"pooled":compare(test,q),"per_league":{k:compare([r for r in test if r["league"]==k],q) for k in v.LEAGUES},
        "uncertainty_coverage_guaranteed":False,"temporal_dependence_and_distribution_shift":True,
        "assessment_previously_inspected":True,"prospective_validation":False,"verified_forward_sample_credit":0,
        "production_recommendations":"DISABLED","automatic_promotion":False,"status":"HOLD"}
def main():
    p=argparse.ArgumentParser()
    for k in ("input-dir","manifest","base-dir","base-manifest","output"):p.add_argument("--"+k,required=True)
    a=p.parse_args();old,_=v.load(a.base_dir,decode(Path(a.base_manifest).read_bytes()));new,_=hx.load(a.input_dir,decode(Path(a.manifest).read_bytes()))
    data=hx.combine(old,new);rows=[]
    for league in v.LEAGUES:
        for season in (*FIT,CAL,TEST):rows+=fold(data,league,season)
    out=evaluate(rows)
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
