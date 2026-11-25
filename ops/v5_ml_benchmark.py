"""V5 phase 4: fixed multi-model chronological research benchmark.
No model selection, deployment, market prices or authenticated live evidence.
Optional ML libraries are imported only when explicitly running the benchmark.
"""
import argparse
from collections import defaultdict
from datetime import date
import hashlib
import json
import math
from pathlib import Path

MODEL="v5-fixed-multiclass-benchmark-v1"
FEATURE_NAMES=("league_home_goals","league_away_goals","home_attack","home_conceded",
               "away_attack","away_conceded","home_points_per_game","away_points_per_game",
               "home_games","away_games","home_recent_points","away_recent_points")
BACKENDS=("logistic","lightgbm","catboost","xgboost")
MIN_TEAM=5
MIN_HISTORY=40

def parse(doc):
    if not isinstance(doc,dict) or not isinstance(doc.get("matches"),list) or len(doc["matches"])>650:
        raise ValueError("INVALID_ARCHIVE")
    out=[];seen=set()
    for r in doc["matches"]:
        if not isinstance(r,dict):raise ValueError("INVALID_ROW")
        h,a=r.get("team1"),r.get("team2")
        if not all(isinstance(t,str) and 0<len(t.strip())<=109 for t in (h,a)) or h==a:raise ValueError("INVALID_TEAMS")
        d=date.fromisoformat(r["date"]);k=(d,h,a)
        if k in seen:raise ValueError("DUPLICATE_FIXTURE")
        seen.add(k)
        if r.get("status")=="canceled" and r.get("score") is None:continue
        s=r.get("score");s=s.get("ft") if isinstance(s,dict) else s
        if not isinstance(s,list) or len(s)!=2 or not all(type(v) is int and 0<=v<=20 for v in s):raise ValueError("INVALID_SCORE")
        out.append((d,h,a,*s))
    return sorted(out)

def features(doc):
    groups=defaultdict(list)
    for r in parse(doc):groups[r[0]].append(r)
    teams=defaultdict(list);prior=[];out=[]
    for day in sorted(groups):
        for _,h,a,x,y in groups[day]:
            H,A=teams[h],teams[a]
            if len(prior)<MIN_HISTORY or min(len(H),len(A))<MIN_TEAM:continue
            def avg(v,i):return sum(x[i] for x in v)/len(v)
            row=[avg(prior,0),avg(prior,1),avg(H,0),avg(H,1),avg(A,0),avg(A,1),
                 avg(H,2),avg(A,2),len(H),len(A),avg(H[-5:],2),avg(A[-5:],2)]
            out.append({"date":day.isoformat(),"home":h,"away":a,"x":row,"y":0 if x>y else 1 if x==y else 2})
        # Features for all fixtures on this date are frozen before updates.
        for _,h,a,x,y in groups[day]:
            teams[h].append((x,y,3 if x>y else 1 if x==y else 0))
            teams[a].append((y,x,3 if y>x else 1 if x==y else 0))
            prior.append((x,y))
    return out

def split(train_doc,test_doc):
    t,a=parse(train_doc),parse(test_doc)
    if not t or not a or max(r[0] for r in t)>=min(r[0] for r in a):raise ValueError("OVERLAPPING_OR_EMPTY_SEASONS")
    train,test=features(train_doc),features(test_doc)
    if len(train)<100 or len(test)<50 or {r["y"] for r in train}!={0,1,2}:raise ValueError("INSUFFICIENT_FEATURE_COHORT")
    return train,test

def classifier(name):
    if name=="logistic":
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        from sklearn.linear_model import LogisticRegression
        return make_pipeline(StandardScaler(),LogisticRegression(C=.3,max_iter=1000,random_state=42))
    if name=="lightgbm":
        from lightgbm import LGBMClassifier
        return LGBMClassifier(objective="multiclass",n_estimators=100,learning_rate=.03,num_leaves=7,min_child_samples=25,reg_lambda=5,random_state=42,n_jobs=1,verbosity=-1)
    if name=="catboost":
        from catboost import CatBoostClassifier
        return CatBoostClassifier(loss_function="MultiClass",iterations=100,depth=3,learning_rate=.03,l2_leaf_reg=5,random_seed=42,thread_count=1,verbose=False,allow_writing_files=False)
    if name=="xgboost":
        from xgboost import XGBClassifier
        return XGBClassifier(objective="multi:softprob",num_class=3,n_estimators=100,max_depth=3,learning_rate=.03,min_child_weight=5,reg_lambda=5,random_state=42,n_jobs=1,eval_metric="mlogloss")
    raise ValueError("UNKNOWN_BACKEND")

def metrics(p,y):
    if len(p)!=len(y) or not y:raise ValueError("INVALID_PREDICTION_COUNT")
    for v in p:
        if len(v)!=3 or not all(math.isfinite(x) and 0<=x<=1 for x in v) or abs(sum(v)-1)>1e-5:raise ValueError("INVALID_PROBABILITY")
    n=len(y)
    return {"n":n,"log_loss":sum(-math.log(max(v[t],1e-15)) for v,t in zip(p,y))/n,
            "brier":sum(sum((x-int(i==t))**2 for i,x in enumerate(v)) for v,t in zip(p,y))/n,
            "correct":sum(max(range(3),key=lambda i:v[i])==t for v,t in zip(p,y)),
            "home_top":sum(max(range(3),key=lambda i:v[i])==0 for v in p)}

def build(train_doc,test_doc):
    train,test=split(train_doc,test_doc)
    x=[r["x"] for r in train];y=[r["y"] for r in train]
    tx=[r["x"] for r in test];ty=[r["y"] for r in test]
    priors=[(y.count(i)+1)/(len(y)+3) for i in range(3)]
    results={"train_frequency":metrics([priors]*len(ty),ty)};missing=[]
    for name in BACKENDS:
        try:model=classifier(name)
        except ImportError:
            missing.append(name);continue
        model.fit(x,y)
        if list(model.classes_)!=[0,1,2]:raise ValueError("CLASS_ORDER_MISMATCH")
        p=[[float(v) for v in r] for r in model.predict_proba(tx)]
        results[name]=metrics(p,ty)
    digest=lambda d:hashlib.sha256(json.dumps(d,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    return {"model_id":MODEL,"status":"HOLD" if missing else "RESEARCH_ONLY","missing_backends":missing,
            "train_n":len(train),"assessment_n":len(test),"actual_home_count":ty.count(0),
            "train_sha256":digest(train_doc),"assessment_sha256":digest(test_doc),
            "features":list(FEATURE_NAMES),"metrics":results,
            "assessment_features_use_only_previous_calendar_day_results":True,
            "assessment_previously_inspected":True,"hyperparameter_search":False,
            "market_comparison_available":False,"prospective_validation":False,
            "source_results_independently_verified":False,"automatic_promotion":False,
            "production_recommendations":"DISABLED"}

def main():
    p=argparse.ArgumentParser();p.add_argument("--train",required=True);p.add_argument("--assessment",required=True);p.add_argument("--output",required=True);a=p.parse_args()
    def read(path):
        f=Path(path)
        if f.stat().st_size>500000:raise ValueError("ARCHIVE_LIMIT")
        return json.loads(f.read_text())
    report=build(read(a.train),read(a.assessment))
    Path(a.output).write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print(json.dumps(report,allow_nan=False))
if __name__=="__main__":main()
