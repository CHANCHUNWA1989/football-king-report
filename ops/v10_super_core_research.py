"""V10 core: causal same-fixture model competition and research-only safety gates."""
import argparse
from collections import defaultdict
from datetime import date,timedelta
import json
import math
from pathlib import Path
import random
from ops.v9_fixed_history_benchmark import load,predict
from ops.v9_chronological_calibration import calibrated,select,IDENTITY

RAW=("prior_poisson","dynamic_poisson","dixon_coles","elo")
MODELS=RAW+("dynamic_calibrated","equal_ensemble","adaptive_ensemble","adaptive_calibrated")
THRESHOLDS=(.50,.55,.60,.65,.70,.75)
def normalize(p):
    if len(p)!=3 or any(not math.isfinite(x) or x<0 for x in p) or sum(p)<=0:
        raise ValueError("INVALID_PROBABILITY")
    return tuple(x/sum(p) for x in p)
def dc(p,rate,rho=-.10):
    # Corrections to 00, 01, 10, 11; use exact normalization of the truncated grid.
    h,a=rate
    mass=math.exp(-h-a)
    from ops.v9_fixed_history_benchmark import poisson
    den=sum(poisson(h))*sum(poisson(a))
    delta=rho*h*a*mass/den
    return normalize((p[0]+delta,p[1]-2*delta,p[2]+delta))
def elo_prob(rh,ra,draw):
    # Davidson three-outcome extension; neutral draw prior from previous season.
    x=10**(max(-1200,min(1200,rh-ra+60))/400)
    d=2*draw/(1-draw)*math.sqrt(x)
    return normalize((x,d,1.))
def elo_replay(train,test):
    if not train or not test or max(r[0] for r in train)>=min(r[0] for r in test):
        raise ValueError("ELO_CHRONOLOGY")
    draw=max(.10,min(.45,sum(r[3]==r[4] for r in train)/len(train)))
    ratings=defaultdict(lambda:1500.)
    def walk(rows):
        by=defaultdict(list)
        for row in rows:by[row[0]].append(row)
        out={}
        for day in sorted(by):
            updates=defaultdict(float)
            for _,h,a,x,y in by[day]:
                key=(day,h,a)
                if key in out:raise ValueError("DUPLICATE_FIXTURE")
                p=elo_prob(ratings[h],ratings[a],draw);out[key]=p
                error=(1. if x>y else .5 if x==y else 0.)-(p[0]+.5*p[1])
                updates[h]+=20*error;updates[a]-=20*error
            for team,delta in updates.items():ratings[team]+=delta
        return out
    walk(train)
    # Partial regression towards the league mean before the new season.
    for team in ratings:ratings[team]=1500+.75*(ratings[team]-1500)
    return walk(test)
def weights(rows):
    if len(rows)<500:return (1/len(RAW),)*len(RAW)
    losses=[sum(-math.log(max(r["p"][m][r["y"]],1e-15)) for r in rows)/len(rows) for m in RAW]
    floor=min(losses)
    v=[math.exp(-8*(x-floor)) for x in losses]
    # Half-shrink to equal weights: don't let a noisy historical winner dominate.
    return tuple(.5/len(RAW)+.5*x/sum(v) for x in v)
def blend(p,w):
    return normalize(tuple(sum(wi*p[m][k] for wi,m in zip(w,RAW)) for k in range(3)))
def calibration_rows(rows,model):
    return [(None,None,None,r["y"],r["p"][model],r["p"][model]) for r in rows]
def score(rows,model):
    n=len(rows)
    if not n:return {"n":0,"correct":0,"accuracy":None,"log_loss":None,"brier":None}
    correct=sum(max(range(3),key=lambda i:r["p"][model][i])==r["y"] for r in rows)
    return {"n":n,"correct":correct,"accuracy":correct/n,
      "log_loss":sum(-math.log(max(r["p"][model][r["y"]],1e-15)) for r in rows)/n,
      "brier":sum(sum((r["p"][model][i]-(i==r["y"]))**2 for i in range(3)) for r in rows)/n}
def all_scores(rows):
    return {m:score(rows,m) for m in MODELS}
def lower_wilson(k,n):
    if not n:return 0.
    z=1.95996398454;p=k/n
    return (p+z*z/(2*n)-z*math.sqrt((p*(1-p)+z*z/(4*n))/n))/(1+z*z/n)
def confidence_rule(prior):
    # Rule chosen exclusively on earlier out-of-fold predictions; no fallback pick.
    if len(prior)<500:return None
    for t in THRESHOLDS:
        chosen=[r for r in prior if max(r["p"]["adaptive_calibrated"])>=t]
        s=score(chosen,"adaptive_calibrated")
        if s["n"]>=150 and s["n"]/len(prior)>=.15 and s["accuracy"]>=.70 and lower_wilson(s["correct"],s["n"])>=.60:
            return t
    return None
def raw_rows(train,test):
    elo=elo_replay(train,test)
    out=[]
    for day,h,a,y,b,c,_,rate in predict(train,test,include_rates=True):
        out.append({"day":day,"h":h,"a":a,"y":y,"p":dict(zip(RAW,(b,c,dc(c,rate),elo[(day,h,a)])))})
    return out
def paired_blocks(rows,model,baseline="dynamic_poisson",seed=104729):
    blocks=defaultdict(lambda:[0,0.,0.])
    for r in rows:
        a,b=r["p"][model],r["p"][baseline];y=r["y"]
        v=blocks[r["year"],r["league"]]
        v[0]+=1;v[1]+=int(max(range(3),key=lambda i:a[i])==y)-int(max(range(3),key=lambda i:b[i])==y)
        v[2]+=math.log(max(a[y],1e-15))-math.log(max(b[y],1e-15))
    vals=list(blocks.values())
    if len(vals)<5:return {"blocks":len(vals),"accuracy_delta_ci":None,"log_loss_reduction_ci":None}
    rng=random.Random(seed);acc=[];ll=[]
    for _ in range(1000):
        draw=rng.choices(vals,k=len(vals));n=sum(v[0] for v in draw)
        acc.append(sum(v[1] for v in draw)/n);ll.append(sum(v[2] for v in draw)/n)
    def interval(v):
        v.sort();return [v[24],v[975]]
    return {"blocks":len(vals),"resamples":1000,"accuracy_delta_ci":interval(acc),"log_loss_reduction_ci":interval(ll),"method":"paired league-season cluster bootstrap; conditional retrospective uncertainty"}
def evaluate(groups,*,return_rows=False):
    prior=defaultdict(list);previous=[];all_rows=[];selected=[];folds=[];rules=[]
    for year in sorted(groups):
        threshold=confidence_rule(previous)
        rules.append({"year":year,"development_n":len(previous),"threshold":threshold})
        current=[]
        for league,rows in sorted(groups[year].items()):
            hist=prior[league];w=weights(hist)
            cp=select(calibration_rows(hist,"dynamic_poisson"))
            ap=select(calibration_rows(hist,"adaptive_ensemble"))
            fold=[]
            for r in rows:
                p=dict(r["p"])
                p["dynamic_calibrated"]=calibrated(p["dynamic_poisson"],cp)
                p["equal_ensemble"]=blend(p,(.25,)*4)
                p["adaptive_ensemble"]=blend(p,w)
                p["adaptive_calibrated"]=calibrated(p["adaptive_ensemble"],ap)
                item={**r,"p":p,"year":year,"league":league}
                fold.append(item)
                if threshold is not None and max(p["adaptive_calibrated"])>=threshold:selected.append(item)
            current.extend(fold)
            folds.append({"year":year,"league":league,"development_n":len(hist),"weights":dict(zip(RAW,w)),"dynamic_calibration":cp,"adaptive_calibration":ap,"scores":all_scores(fold)})
        # No test season can contribute to its own weights, calibration or threshold.
        for r in current:prior[r["league"]].append(r)
        previous.extend(current);all_rows.extend(current)
    latest=[r for r in all_rows if r["year"]==2025]
    same50=[r for r in latest if max(r["p"]["dynamic_poisson"])>=.5]
    scores=all_scores(all_rows);ci=paired_blocks(all_rows,"adaptive_calibrated")
    final=scores["adaptive_calibrated"];base=scores["dynamic_poisson"]
    screen=bool(final["n"] and ci["log_loss_reduction_ci"] and ci["log_loss_reduction_ci"][0]>0 and final["accuracy"]>=base["accuracy"] and final["brier"]<=base["brier"])
    report={"schema":"football-king-v10-super-core-research-v1","rolling":scores,"latest":all_scores(latest),
      "latest_same_dynamic_50_cohort":{"scores":all_scores(same50),"coverage":len(same50)/len(latest) if latest else None},
      "causal_confidence_selection":{"rules":rules,"scores":all_scores(selected),"coverage":len(selected)/len(all_rows) if all_rows else None},
      "paired_adaptive_calibrated_vs_dynamic":ci,"research_screen_passed":screen,"folds":folds,
      "model_names":MODELS,"same_day_updates_after_forecasts":True,"assessment_previously_inspected":True,
      "independent_assessment_count":0,"verified_forward_sample_credit":0,"actual_xg_verified":False,"market_ev_verified":False,
      "automatic_promotion":False,"production_recommendations":"DISABLED","status":"HOLD"}
    return (report,all_rows) if return_rows else report
def build(data):
    groups=defaultdict(dict)
    for (year,league),test in sorted(data.items()):
        train=data.get((year-1,league))
        if train is not None and len(train)>=100 and test:groups[year][league]=raw_rows(train,test)
    result=evaluate(groups)
    result["history_finished"]=sum(map(len,data.values()))
    return result
def selftest():
    from ops.v9_fixed_history_benchmark import probs
    p=probs(1.5,1.1);q=dc(p,(1.5,1.1))
    assert abs(sum(q)-1)<1e-12 and q[1]>p[1]
    assert all(x>0 for x in dc(probs(8,8),(8,8)))
    tr=[(date(2018,8,1)+timedelta(days=i),"A","B",2,1) for i in range(100)]
    test=[(date(2019,8,1),"A","B",1,0),(date(2019,8,1),"B","C",0,2),(date(2019,8,2),"A","B",2,1)]
    changed=[(*test[0][:3],0,5),*test[1:]]
    a,b=raw_rows(tr,test),raw_rows(tr,changed)
    assert [r["p"] for r in a[:2]]==[r["p"] for r in b[:2]]
    assert a[2]["p"]["elo"]!=b[2]["p"]["elo"]
    assert weights([])==(.25,)*4 and confidence_rule([]) is None
    res=evaluate({2024:{"L":a},2025:{"L":b}})
    assert res["rolling"]["dynamic_poisson"]["n"]==6 and res["independent_assessment_count"]==0
    assert res["status"]=="HOLD" and res["automatic_promotion"] is False
    assert res["folds"][1]["development_n"]==3 and res["folds"][0]["development_n"]==0
    return 8
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--root",required=True);parser.add_argument("--manifest",required=True);parser.add_argument("--output")
    a=parser.parse_args();tested=selftest();r=build(load(a.root,json.loads(Path(a.manifest).read_text())))
    if r["history_finished"]!=30273 or any(s["n"]!=27835 for s in r["rolling"].values()):raise ValueError("PINNED_COHORT_MISMATCH")
    result={"synthetic_checks":tested,**r}
    if a.output:
        with Path(a.output).open("x",encoding="utf-8") as f:json.dump(result,f,allow_nan=False,sort_keys=True)
    print(json.dumps({k:v for k,v in result.items() if k!="folds"},allow_nan=False,sort_keys=True))
