"""Retrospective fixed-line probability audit, not observed market or profit replay."""
from math import fsum,log
from pathlib import Path
from ops.historical_dc_replay_20261127 import EXTRA,dated_rates,fit,tau
from ops.historical_fair_model_replay_20261127 import TeamCounts
from ops.historical_recency_replay_20261127 import MANIFEST,load_regular
from ops.historical_season_replay_20261127 import load_season
from ops.live_score_challenger_20261127 import score_grid
from ops.live_unified_market_probabilities_20261127 import unified_markets,OUTCOMES
from ops.live_snapshot_market_audit_20261126 import legs

AH=(-.25,-.75,-1.25,-1.75,.25,.75)
OU=(1.75,2.25,2.75,3.25,3.75)
LINES=tuple(("AH",x) for x in AH)+tuple(("OU",x) for x in OU)
METRICS=("log_loss","brier","rps")

def realized(margin,line):
    a,b=legs(line)
    return 2-sum((margin+x>0)-(margin+x<0) for x in (a,b))

def loss(dist,y):
    p=[dist[k] for k in OUTCOMES]
    if not 0<=y<5 or min(p)<0 or abs(fsum(p)-1)>1e-10:
        raise ValueError("invalid settlement distribution")
    return (-log(max(p[y],1e-15)),fsum((v-(i==y))**2 for i,v in enumerate(p)),
            fsum((fsum(p[:i+1])-(y<=i))**2 for i in range(4))/4)

def market_losses(grid,final):
    markets=unified_markets(grid,AH,OU,scope="FULL_MATCH")
    h,a=final
    return [loss(x["home"],realized(h-a,x["home_line"])) for x in markets["handicaps"]]+[
            loss(x["over"],realized(h+a,-x["line"])) for x in markets["totals"]]

def evaluate(train,cal,test):
    if not train or not cal or not test or max(r[0] for r in train)>=min(r[0] for r in cal) or max(r[0] for r in cal)>=min(r[0] for r in test):
        raise ValueError("strict three-season separation required")
    pool=[fsum(r[3][i] for r in train)/len(train) for i in (0,1)]
    if min(pool)<=0: raise ValueError("invalid pool")
    counts=TeamCounts(pool);counts.update(train)
    rho,_=fit(dated_rates(cal,counts))
    accum=[[[],[]] for _ in LINES];fallback=0
    for mu,f in dated_rates(test,counts):
        r=rho
        if min(tau(mu,r))<=0: r=0;fallback+=1
        for k,rr in enumerate((0,r)):
            for i,v in enumerate(market_losses(score_grid((0,0),*mu,rr),f)):
                accum[i][k].append(v)
    return {"test":len(test),"rho":rho,"fallback":fallback,
            "lines":[{"kind":kind,"line":line,"metrics":[
                {m:fsum(v[j] for v in rows)/len(test) for j,m in enumerate(METRICS)}
                for rows in accum[i]]} for i,(kind,line) in enumerate(LINES)],
            "actual_market_quotes":False,"positive_ev_verified":False,
            "retrospective_only":True,"deployment":"HOLD","recommendations":"DISABLED"}

def run(root):
    reports={}
    for league in ("NL","PT"):
        name,n,*blobs=EXTRA[league]
        rows=[load_season((root/s/name).read_bytes(),b) for s,b in zip(("2022-23","2023-24","2024-25"),blobs)]
        if any(len(r)!=n for r in rows): raise ValueError("incomplete source")
        reports[league]=evaluate(*rows)
    for league,(name,raw_n,regular_n,blobs) in MANIFEST.items():
        rows=[load_regular((root/s/name).read_bytes(),b,raw_n,regular_n)
              for s,b in zip(("2022-23","2023-24","2024-25"),blobs)]
        reports[league]=evaluate(*rows)
    n=sum(r["test"] for r in reports.values())
    return {"reports":reports,"test":n,"correlated_line_observations":n*len(LINES),
            "lines":[{"kind":kind,"line":line,"metrics":[
                {m:fsum(r["lines"][i]["metrics"][k][m]*r["test"] for r in reports.values())/n
                 for m in METRICS} for k in range(2)]} for i,(kind,line) in enumerate(LINES)],
            "scope":"FULL_MATCH","actual_market_quotes":False,"positive_ev_verified":False,
            "prospective_verified":False,"confidence_interval_verified":False,
            "deployment":"HOLD","recommendations":"DISABLED"}

if __name__=="__main__":
    from argparse import ArgumentParser
    from json import dumps
    p=ArgumentParser();p.add_argument("root",type=Path)
    print(dumps(run(p.parse_args().root),indent=2))
