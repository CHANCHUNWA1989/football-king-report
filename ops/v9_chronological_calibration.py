"""Chronological calibration challenger on previously inspected historical data only."""
import argparse
from collections import defaultdict
import itertools
import json
import math
from pathlib import Path
from ops.v9_fixed_history_benchmark import load,predict,metrics

GRID=tuple(itertools.product((.8,1.,1.2),(-.15,0.,.15),(-.2,0.,.2)))
IDENTITY=(1.,0.,0.)
def calibrated(p,params):
    t,h,d=params
    z=[math.log(max(v,1e-15))/t+b for v,b in zip(p,(h,d,0.))]
    m=max(z);v=[math.exp(x-m) for x in z]
    return tuple(x/sum(v) for x in v)
def select(rows):
    if len(rows)<500:return IDENTITY
    def loss(q):
        return sum(-math.log(calibrated(r[5],q)[r[3]]) for r in rows)/len(rows)
    return min(GRID,key=lambda q:(loss(q),sum(abs(a-b) for a,b in zip(q,IDENTITY)),q))
def evaluate(groups):
    prior=defaultdict(list);out=[];folds=[];recent=[]
    for year in sorted(groups):
        # Freeze from strictly earlier seasons, including all leagues on the same year.
        for league,rows in sorted(groups[year].items()):
            params=select(prior[league])
            transformed=[(*r[:4],r[5],calibrated(r[5],params)) for r in rows]
            out.extend(transformed)
            if year==2025:recent.extend(transformed)
            folds.append({"year":year,"league":league,"development_n":len(prior[league]),"params":params,**metrics(transformed)})
        for league,rows in groups[year].items():prior[league].extend(rows)
    selected=[r for r in recent if max(r[4])>=.5]
    return {"schema":"v9-chronological-calibration-research-v1","rolling":metrics(out),"latest":metrics(recent),
      "same_uncalibrated_threshold_50":{**metrics(selected),"coverage":len(selected)/len(recent) if recent else None},
      "folds":folds,"grid_size":len(GRID),"selection_metric":"prior season pooled within league log loss",
      "baseline_definition":"uncalibrated dynamic Poisson from fixed benchmark",
      "assessment_previously_inspected":True,"independent_assessment_count":0,"verified_forward_sample_credit":0,
      "automatic_promotion":False,"production_recommendations":"DISABLED","status":"HOLD"}
def build(data):
    groups=defaultdict(dict)
    for (year,league),test in sorted(data.items()):
        train=data.get((year-1,league))
        if train is not None and len(train)>=100 and test:groups[year][league]=predict(train,test)
    return evaluate(groups)
def selftest():
    p=(.6,.2,.2)
    assert all(abs(a-b)<1e-12 for a,b in zip(calibrated(p,IDENTITY),p))
    assert abs(sum(calibrated(p,(.8,.15,-.2)))-1)<1e-12
    row=(None,"A","B",1,p,p)
    a=evaluate({2024:{"L":[row]*500},2025:{"L":[row]}})
    b=evaluate({2024:{"L":[row]*500},2025:{"L":[(*row[:3],0,*row[4:])]}})
    assert a["folds"][1]["params"]==b["folds"][1]["params"]
    assert a["folds"][0]["development_n"]==0 and a["folds"][0]["params"]==IDENTITY
    assert a["folds"][1]["development_n"]==500
    return 5
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",required=True);p.add_argument("--manifest",required=True)
    a=p.parse_args();result=build(load(a.root,json.loads(Path(a.manifest).read_text())))
    print(json.dumps({"synthetic_checks":selftest(),**result},allow_nan=False,sort_keys=True))
