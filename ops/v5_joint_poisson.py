"""V5 phase 3: joint penalized Poisson attack/defence and home effect.
Fixed optimization protocol. Archive replay only; no source authentication.
"""
import argparse
from collections import Counter
from datetime import date
import hashlib
import json
import math
from pathlib import Path

MODEL = "v5-joint-ridge-poisson-v1"
RIDGE = 4.0
ITERATIONS = 150
STEP = .5
MIN_HISTORY = 100
MIN_TEAM = 5

def parse(doc):
    if not isinstance(doc,dict) or not isinstance(doc.get("matches"),list) or len(doc["matches"])>650:
        raise ValueError("INVALID_ARCHIVE")
    rows,seen=[],set()
    for r in doc["matches"]:
        if not isinstance(r,dict):
            raise ValueError("INVALID_ROW")
        h,a=r.get("team1"),r.get("team2")
        if not all(isinstance(t,str) and 0<len(t.strip())<=109 for t in (h,a)) or h==a:
            raise ValueError("INVALID_TEAM")
        day=date.fromisoformat(r["date"])
        key=(day,h,a)
        if key in seen:
            raise ValueError("DUPLICATE_FIXTURE")
        seen.add(key)
        if r.get("status")=="canceled" and r.get("score") is None:
            continue
        s=r.get("score")
        s=s.get("ft") if isinstance(s,dict) else s
        if not isinstance(s,list) or len(s)!=2 or not all(type(v) is int and 0<=v<=20 for v in s):
            raise ValueError("INVALID_SCORE")
        rows.append((day,h,a,*s))
    return sorted(rows)

def objective(rows,b,venue,att,defence):
    total=0.
    for _,h,a,x,y in rows:
        for z,g in ((b+venue+att[h]+defence[a],x),(b+att[a]+defence[h],y)):
            total+=math.exp(z)-g*z
    return total+RIDGE/2*(venue**2+sum(v*v for v in att.values())+sum(v*v for v in defence.values()))

def fit(rows,cutoff):
    if len(rows)<MIN_HISTORY or any(r[0]>=cutoff for r in rows):
        raise ValueError("INSUFFICIENT_OR_NONPRIOR_HISTORY")
    counts=Counter(t for _,h,a,_,_ in rows for t in (h,a))
    teams=sorted(counts)
    att=dict.fromkeys(teams,0.)
    defence=dict.fromkeys(teams,0.)
    b=math.log(max(.2,sum(r[3]+r[4] for r in rows)/(2*len(rows))))
    venue=0.
    initial=objective(rows,b,venue,att,defence)
    prev=initial
    for _ in range(ITERATIONS):
        gb=0.;gv=RIDGE*venue
        ga={t:RIDGE*att[t] for t in teams};gd={t:RIDGE*defence[t] for t in teams}
        for _,h,a,x,y in rows:
            eh=math.exp(b+venue+att[h]+defence[a])-x
            ea=math.exp(b+att[a]+defence[h])-y
            gb+=eh+ea;gv+=eh;ga[h]+=eh;ga[a]+=ea;gd[a]+=eh;gd[h]+=ea
        step=STEP
        for retry in range(20):
            nb=b-step*gb/(2*len(rows));nv=venue-step*gv/(len(rows)+RIDGE)
            na={t:att[t]-step*ga[t]/(counts[t]+RIDGE) for t in teams}
            nd={t:defence[t]-step*gd[t]/(counts[t]+RIDGE) for t in teams}
            # Center the team effects, preserving both log rates exactly.
            ma=sum(na.values())/len(teams);md=sum(nd.values())/len(teams)
            na={t:v-ma for t,v in na.items()};nd={t:v-md for t,v in nd.items()};nb+=ma+md
            if max(abs(nb),abs(nv),*(abs(v) for v in na.values()),*(abs(v) for v in nd.values()))>10:
                step/=2;continue
            val=objective(rows,nb,nv,na,nd)
            if val<=prev+1e-10:
                break
            step/=2
        else:
            raise ValueError("OPTIMIZER_FAILED")
        b,venue,att,defence=nb,nv,na,nd
        if prev-val<1e-8:
            prev=val;break
        prev=val
    return {"intercept":b,"home_effect":venue,"attack":att,"defence":defence,
            "counts":dict(counts),"initial_objective":initial,"final_objective":prev}

def rates(model,h,a):
    if h==a or min(model["counts"].get(h,0),model["counts"].get(a,0))<MIN_TEAM:
        return None
    b=model["intercept"];v=model["home_effect"];att=model["attack"];d=model["defence"]
    return (math.exp(b+v+att[h]+d[a]),math.exp(b+att[a]+d[h]))

def probability(rates):
    if not all(math.isfinite(v) and .05<=v<=8 for v in rates):
        raise ValueError("RATE_OUTSIDE_RESEARCH_RANGE")
    grids=[]
    for lam in rates:
        p=[math.exp(-lam)]
        for k in range(1,25):p.append(p[-1]*lam/k)
        grids.append(p)
    out=[0.,0.,0.]
    for i,x in enumerate(grids[0]):
        for j,y in enumerate(grids[1]):
            out[0 if i>j else 1 if i==j else 2]+=x*y
    return [v/sum(out) for v in out]

def summary(rows,key):
    if not rows:return None
    n=len(rows)
    return {"n":n,"log_loss":sum(-math.log(max(r[key][r["y"]],1e-15)) for r in rows)/n,
            "brier":sum(sum((p-int(i==r["y"]))**2 for i,p in enumerate(r[key])) for r in rows)/n,
            "correct":sum(max(range(3),key=lambda i:r[key][i])==r["y"] for r in rows),
            "home_top":sum(max(range(3),key=lambda i:r[key][i])==0 for r in rows)}

def build(train_doc,test_doc):
    train,test=parse(train_doc),parse(test_doc)
    if not test or not train or max(r[0] for r in train)>=min(r[0] for r in test):
        raise ValueError("OVERLAPPING_OR_EMPTY_SEASONS")
    model=fit(train,min(r[0] for r in test))
    # Frozen historical league-average comparator; identical fixtures.
    lh=max(.05,sum(r[3] for r in train)/len(train));la=max(.05,sum(r[4] for r in train)/len(train))
    base=probability((lh,la));cases=[];excluded=Counter()
    for day,h,a,x,y in test:
        r=rates(model,h,a)
        if r is None:excluded["unseen_or_sparse_team"]+=1;continue
        if not all(.05<=v<=8 for v in r):excluded["rate_outside_range"]+=1;continue
        cases.append({"date":day.isoformat(),"home":h,"away":a,"y":0 if x>y else 1 if x==y else 2,
                      "candidate":probability(r),"baseline":base})
    digest=lambda d:hashlib.sha256(json.dumps(d,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    return {"model_id":MODEL,"status":"RESEARCH_ONLY" if cases else "HOLD","train_sha256":digest(train_doc),
            "assessment_sha256":digest(test_doc),"train_n":len(train),"assessment_n":len(test),
            "excluded":dict(excluded),"fit":model,"candidate":summary(cases,"candidate"),
            "league_average_baseline":summary(cases,"baseline"),"cases":cases,
            "assessment_previously_inspected":True,"prospective_validation":False,
            "source_results_independently_verified":False,"market_comparison_available":False,
            "automatic_promotion":False,"production_recommendations":"DISABLED"}

def main():
    p=argparse.ArgumentParser();p.add_argument("--train",required=True);p.add_argument("--assessment",required=True);p.add_argument("--output",required=True);a=p.parse_args()
    def read(path):
        f=Path(path)
        if f.stat().st_size>500000:raise ValueError("ARCHIVE_LIMIT")
        return json.loads(f.read_text())
    report=build(read(a.train),read(a.assessment))
    Path(a.output).write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ("cases","fit")}))
if __name__=="__main__":main()
