"""Retrospective independent NB2 score challenger; no market-price replay."""
from math import exp,fsum,log,log1p,isfinite
from pathlib import Path
from ops.historical_dc_replay_20261127 import EXTRA,dated_rates
from ops.historical_fair_model_replay_20261127 import TeamCounts
from ops.historical_recency_replay_20261127 import MANIFEST,load_regular
from ops.historical_season_replay_20261127 import load_season
from ops.historical_asian_probability_replay_20261127 import realized,loss
from ops.live_unified_market_probabilities_20261127 import unified_markets

ALPHAS=(0,.025,.05,.1,.2,.4)
AH=(-1.25,-1.75,-2.25)
OU=(2.75,3.25,3.75,4.75)
METRICS=("exact","one","tail_p","tail_brier","deep","ou","tail_actual")
TAIL_TOL=5e-13

def pmf(mu,alpha):
    if type(mu) not in (int,float) or not isfinite(mu) or not 0<=mu<=12 or alpha not in ALPHAS:
        raise ValueError("unsupported parameters")
    p=[exp(-mu if alpha==0 else -log1p(alpha*mu)/alpha)]
    for i in range(1,201):
        p.append(p[-1]*mu*(1+alpha*(i-1))/(i*(1+alpha*mu)))
        if i>=30:
            r=max(mu*(1+alpha*i)/((i+1)*(1+alpha*mu)),alpha*mu/(1+alpha*mu))
            if r<1 and p[-1]*r/(1-r)<TAIL_TOL:
                mass=fsum(p)
                if abs(mass-1)>1e-10: raise ArithmeticError("mass drift")
                return [v/mass for v in p]
    raise ArithmeticError("tail bound not reached")

def exact_loss(mu,f,alpha):
    h,a=(pmf(m,alpha) for m in mu)
    return -log(max(1e-15,h[f[0]]*a[f[1]]))

def fit(rows):
    if not rows: raise ValueError("empty calibration")
    scores={a:fsum(exact_loss(mu,f,a) for mu,f in rows)/len(rows) for a in ALPHAS}
    return min(ALPHAS,key=scores.__getitem__),scores

def evaluate_model(rows,alpha):
    values=[];hits=0
    for mu,f in rows:
        h,a=(pmf(m,alpha) for m in mu)
        grid={(i,j):x*y for i,x in enumerate(h) for j,y in enumerate(a)}
        markets=unified_markets(grid,AH,OU,scope="FULL_MATCH")
        p=markets["one_x_two"];y=0 if f[0]>f[1] else 1 if f[0]==f[1] else 2
        hits+=int(max(range(3),key=p.__getitem__)==y)
        t=fsum(v for (i,j),v in grid.items() if i+j>=5);actual=int(sum(f)>=5)
        deep=fsum(loss(x["home"],realized(f[0]-f[1],x["home_line"]))[0] for x in markets["handicaps"])/len(AH)
        ou=fsum(loss(x["over"],realized(sum(f),-x["line"]))[0] for x in markets["totals"])/len(OU)
        values.append((exact_loss(mu,f,alpha),-log(max(1e-15,p[y])),t,(t-actual)**2,deep,ou,actual))
    return {**{m:fsum(v[i] for v in values)/len(rows) for i,m in enumerate(METRICS)},"hits":hits}

def replay(train,cal,test):
    if not train or not cal or not test or max(r[0] for r in train)>=min(r[0] for r in cal) or max(r[0] for r in cal)>=min(r[0] for r in test):
        raise ValueError("strict three-season separation required")
    pool=[fsum(r[3][i] for r in train)/len(train) for i in (0,1)]
    if min(pool)<=0: raise ValueError("invalid pool")
    counts=TeamCounts(pool);counts.update(train)
    alpha,scores=fit(dated_rates(cal,counts))
    rows=dated_rates(test,counts)
    baseline=evaluate_model(rows,0)
    candidate=baseline if alpha==0 else evaluate_model(rows,alpha)
    return {"test":len(test),"alpha":alpha,"calibration_scores":scores,
            "baseline":baseline,"candidate":candidate,"positive_ev_verified":False,
            "deployment":"HOLD","recommendations":"DISABLED"}

def run(root):
    reports={}
    seasons=("2022-23","2023-24","2024-25")
    for league in ("NL","PT"):
        name,n,*blobs=EXTRA[league]
        rows=[load_season((root/s/name).read_bytes(),b) for s,b in zip(seasons,blobs)]
        if any(len(r)!=n for r in rows): raise ValueError("incomplete source")
        reports[league]=replay(*rows)
    for league,(name,raw_n,regular_n,blobs) in MANIFEST.items():
        reports[league]=replay(*[load_regular((root/s/name).read_bytes(),b,raw_n,regular_n)
                                 for s,b in zip(seasons,blobs)])
    n=sum(r["test"] for r in reports.values())
    return {"reports":reports,"test":n,"combined":{k:{
        **{m:fsum(r[k][m]*r["test"] for r in reports.values())/n for m in METRICS},
        "hits":sum(r[k]["hits"] for r in reports.values())} for k in ("baseline","candidate")},
        "retrospective_only":True,"actual_market_quotes":False,"prospective_verified":False,
        "confidence_interval_verified":False,"positive_ev_verified":False,
        "deployment":"HOLD","recommendations":"DISABLED"}

if __name__=="__main__":
    from argparse import ArgumentParser
    from json import dumps
    p=ArgumentParser();p.add_argument("root",type=Path)
    print(dumps(run(p.parse_args().root),indent=2))
