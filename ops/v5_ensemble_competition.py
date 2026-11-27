"""V5 phase 7: fixed same-fixture retrospective model competition.
Pinned independent PR implementations, separate live cohort. No promotion.
"""
import argparse
from datetime import date
import importlib.util
import json
import math
from pathlib import Path
import random
from collections import defaultdict

MODEL="v5-pinned-ensemble-competition-v1"
NAMES=("joint_poisson","dixon_coles","dynamic_elo","logistic","lightgbm","catboost","xgboost")
CUT="2026-01-01"
MIN_COHORT=100

def vec(p):
    if not isinstance(p,(list,tuple)) or len(p)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=1 for x in p) or abs(sum(p)-1)>1e-5:
        raise ValueError("BAD_PROBABILITIES")
    return [x/sum(p) for x in p]

def key(r):
    return (r["date"],r["home"],r["away"])

def indexed(rows):
    out={}
    for r in rows:
        k=key(r)
        date.fromisoformat(k[0])
        if k in out:raise ValueError("DUPLICATE_CASE")
        if type(r["y"]) is not int or r["y"] not in (0,1,2):raise ValueError("BAD_RESULT")
        out[k]=r
    return out

def dc(h,a):
    # Fixed low-score rho; no holdout fitting, normalize exact same grid.
    rho=-.05
    def pois(l):
        p=[math.exp(-l)]
        for i in range(1,25):p.append(p[-1]*l/i)
        return p
    out=[0.,0.,0.]
    for i,x in enumerate(pois(h)):
        for j,y in enumerate(pois(a)):
            tau={(0,0):1-h*a*rho,(0,1):1+h*rho,(1,0):1+a*rho,(1,1):1-rho}.get((i,j),1.)
            if tau<=0:raise ValueError("INVALID_DC_CORRECTION")
            out[0 if i>j else 1 if i==j else 2]+=x*y*tau
    return vec([x/sum(out) for x in out])

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def league_cases(league,train,test,joint,elo,ml):
    tr,te=joint.parse(train),joint.parse(test)
    if not tr or not te or max(r[0] for r in tr)>=min(r[0] for r in te):
        raise ValueError("OVERLAPPING_SEASONS")
    jm=joint.fit(tr,min(r[0] for r in te))
    # Phase 2 parser rejects canceled rows, so omit ONLY explicitly canceled no-score rows.
    cleaned={**test,"matches":[r for r in test["matches"] if not(r.get("status")=="canceled" and r.get("score") is None)]}
    er=indexed(elo.replay(cleaned))
    mt,me=ml.split(train,test)
    me=indexed(me); mk=sorted(me)
    probs={}
    for name in ml.BACKENDS:
        m=ml.classifier(name)
        m.fit([r["x"] for r in mt],[r["y"] for r in mt])
        if list(m.classes_)!=[0,1,2]:raise ValueError("BAD_CLASS_ORDER")
        p=m.predict_proba([me[k]["x"] for k in mk])
        if len(p)!=len(mk):raise ValueError("BAD_PREDICTION_LENGTH")
        probs[name]={k:vec([float(v) for v in row]) for k,row in zip(mk,p)}
    result=[];excluded=0
    for day,h,a,x,y in te:
        k=(day.isoformat(),h,a)
        rates=joint.rates(jm,h,a)
        if rates is None or any(not .05<=v<=8 for v in rates) or k not in er or k not in me:
            excluded+=1;continue
        outcome=0 if x>y else 1 if x==y else 2
        if er[k]["y"]!=outcome or me[k]["y"]!=outcome:raise ValueError("OUTCOME_CONFLICT")
        p={"joint_poisson":vec(joint.probability(rates)),"dixon_coles":dc(*rates),
           "dynamic_elo":vec(er[k]["candidate"]),**{name:probs[name][k] for name in ml.BACKENDS}}
        result.append({"league":league,"date":k[0],"home":h,"away":a,"y":outcome,"p":p})
    return result,{"eligible":len(result),"excluded":excluded,"assessment_finished":len(te)}

def weights():
    n=len(NAMES)
    return [("equal",{k:1/n for k in NAMES})]+[
        ("half_"+name,{k:(.5 if k==name else .5/(n-1)) for k in NAMES}) for name in NAMES]

def blend(p,w):
    if set(p)!=set(NAMES) or set(w)!=set(NAMES) or abs(sum(w.values())-1)>1e-8:
        raise ValueError("BAD_MODEL_SET")
    return vec([sum(w[k]*p[k][i] for k in NAMES) for i in range(3)])

def loss(p,y):return -math.log(max(p[y],1e-15))

def metrics(rows,fn):
    if not rows:return None
    vals=[(fn(r),r["y"]) for r in rows]
    n=len(vals)
    return {"n":n,"log_loss":sum(loss(p,y) for p,y in vals)/n,
            "brier":sum(sum((v-int(i==y))**2 for i,v in enumerate(p)) for p,y in vals)/n,
            "correct":sum(max(range(3),key=lambda i:p[i])==y for p,y in vals),
            "home_top":sum(max(range(3),key=lambda i:p[i])==0 for p,y in vals),
            "actual_home":sum(y==0 for p,y in vals)}

def ci(rows,w,ref):
    blocks=defaultdict(list)
    for r in rows:
        week=date.fromisoformat(r["date"]).strftime("%G-W%V")
        blocks[week].append(loss(r["p"][ref],r["y"])-loss(blend(r["p"],w),r["y"]))
    groups=list(blocks.values())
    if len(groups)<12:return None
    rng=random.Random(20261125);samples=[]
    for _ in range(400):
        values=[v for g in rng.choices(groups,k=len(groups)) for v in g]
        samples.append(sum(values)/len(values))
    samples.sort()
    return [samples[10],samples[389]]

def evaluate(rows):
    seen=set()
    for r in rows:
        k=(r["league"],*key(r))
        if k in seen or type(r["y"]) is not int or r["y"] not in (0,1,2):raise ValueError("DUPLICATE_OR_INVALID_CASE")
        seen.add(k);date.fromisoformat(r["date"])
        if set(r["p"])!=set(NAMES):raise ValueError("MISSING_MODEL")
        for v in r["p"].values():vec(v)
    dev=[r for r in rows if r["date"]<CUT];test=[r for r in rows if r["date"]>=CUT]
    out={"model_id":MODEL,"status":"HOLD","selection_cutoff":CUT,
         "development_n":len(dev),"assessment_n":len(test),"selected_weights":None,
         "prospective_validation":False,"assessment_previously_inspected":True,
         "market_comparison_available":False,"independently_verified_results":False,
         "automatic_promotion":False,"production_recommendations":"DISABLED"}
    if min(len(dev),len(test))<MIN_COHORT:return out
    name,w=min(weights(),key=lambda nw:(metrics(dev,lambda r:blend(r["p"],nw[1]))["log_loss"],nw[0]))
    ref=min(NAMES,key=lambda k:(metrics(dev,lambda r:r["p"][k])["log_loss"],k))
    out.update(status="RESEARCH_ONLY",selected_weights=w,selected_grid_name=name,
               development_best_single=ref,
               development_metrics={k:metrics(dev,lambda r:r["p"][k]) for k in NAMES},
               assessment_metrics={**{k:metrics(test,lambda r:r["p"][k]) for k in NAMES},
                  "equal_ensemble":metrics(test,lambda r:blend(r["p"],weights()[0][1])),
                  "selected_ensemble":metrics(test,lambda r:blend(r["p"],w))},
               paired_week_block_ci_vs_development_best=ci(test,w,ref),
               positive_ci_means_ensemble_better=True)
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument("--input-dir",required=True);p.add_argument("--joint",required=True)
    p.add_argument("--elo",required=True);p.add_argument("--ml",required=True);p.add_argument("--output",required=True);a=p.parse_args()
    joint=load(a.joint,"joint");elo=load(a.elo,"elo");ml=load(a.ml,"ml")
    rows=[];scope={}
    for league in ("en.1","de.1","fr.1"):
        def read(season):
            f=Path(a.input_dir)/(season+"-"+league+".json")
            if f.stat().st_size>500000:raise ValueError("ARCHIVE_TOO_LARGE")
            return json.loads(f.read_text())
        r,s=league_cases(league,read("2024-25"),read("2025-26"),joint,elo,ml)
        rows+=r;scope[league]=s
    out=evaluate(rows);out["scope"]=scope
    Path(a.output).write_text(json.dumps(out,indent=2,allow_nan=False)+"\n")
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
