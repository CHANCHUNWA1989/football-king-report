"""Research-only score distribution and paired forecast evaluation.
Caller-supplied remaining goal means are hypotheses, not live xG or fitted rates.
"""
from math import exp, isfinite, fsum, log
from collections.abc import Mapping
from ops.live_snapshot_market_audit_20261126 import aware

def number(x):
    return type(x) in (int,float) and isfinite(x)

def poisson(mu):
    if not number(mu) or not 0 <= mu <= 12:
        raise ValueError("unsupported remaining mean")
    p=[exp(-mu)]
    for k in range(1,81):
        p.append(p[-1]*mu/k)
    if abs(fsum(p)-1)>1e-12:
        raise ArithmeticError("tail bound failed")
    return p

def score_grid(score, home_mean, away_mean, rho=0):
    if not isinstance(score,(tuple,list)) or len(score)!=2 or any(
        type(v) is not int or not 0<=v<=30 for v in score):
        raise ValueError("invalid current score")
    h,a=poisson(home_mean),poisson(away_mean)
    if not number(rho) or abs(rho)>1:
        raise ValueError("invalid rho")
    # Dixon-Coles adjustment for remaining goals; live application is an
    # uncalibrated challenger, not a demonstrated extension of prematch DC.
    tau={(0,0):1-home_mean*away_mean*rho,(0,1):1+home_mean*rho,
         (1,0):1+away_mean*rho,(1,1):1-rho}
    if min(tau.values())<0:
        raise ValueError("negative adjusted probability")
    grid={(score[0]+i,score[1]+j):x*y*tau.get((i,j),1)
          for i,x in enumerate(h) for j,y in enumerate(a)}
    mass=fsum(grid.values())
    if abs(mass-1)>1e-12:
        raise ArithmeticError("probability mass drift")
    return {k:v/mass for k,v in grid.items()}

def summarize(grid):
    h=fsum(p for (i,j),p in grid.items() if i>j)
    d=fsum(p for (i,j),p in grid.items() if i==j)
    a=fsum(p for (i,j),p in grid.items() if i<j)
    return {"one_x_two":(h,d,a),
            "total_at_most_one":fsum(p for (i,j),p in grid.items() if i+j<=1),
            "total_at_most_two":fsum(p for (i,j),p in grid.items() if i+j<=2),
            "deployment":"HOLD","recommendations":"DISABLED",
            "fitted":False,"positive_ev_verified":False}

def _prob(x):
    if not isinstance(x,(list,tuple)) or len(x)!=3 or any(
        not number(v) or not 0<=v<=1 for v in x) or abs(fsum(x)-1)>1e-9:
        raise ValueError("invalid forecast vector")
    return x

def paired_evaluate(rows):
    """One predeclared decision per fixture, identical paired target.
    Timestamp assertions alone do not prove source authenticity or no leakage.
    """
    if not isinstance(rows,list) or not rows:
        raise ValueError("empty cohort")
    seen=set()
    differences=[]
    for r in rows:
        if not isinstance(r,Mapping):
            raise ValueError("invalid row")
        fid=r.get("fixture_id")
        if not isinstance(fid,str) or not fid.strip() or fid in seen:
            raise ValueError("missing or duplicate fixture")
        seen.add(fid)
        cutoff=aware(r.get("decision_at"))
        settled=aware(r.get("settled_at"))
        if not cutoff<settled:
            raise ValueError("settlement not after decision")
        for name in ("baseline","challenger"):
            if not (aware(r.get(name+"_trained_through"))<=aware(r.get(name+"_issued_at")) and aware(r.get(name+"_trained_through"))<cutoff):
                raise ValueError("training cutoff leakage")
            if not aware(r.get(name+"_features_through"))<=aware(r.get(name+"_issued_at"))<=cutoff:
                raise ValueError("feature or forecast chronology leakage")
        b,c=_prob(r.get("baseline")),_prob(r.get("challenger"))
        y=r.get("outcome")
        if type(y) is not int or y not in (0,1,2):
            raise ValueError("invalid outcome")
        def scores(p):
            return (-log(max(p[y],1e-15)),fsum((v-(i==y))**2 for i,v in enumerate(p)),
                    ((p[0]-(y==0))**2+(p[0]+p[1]-(y<=1))**2)/2)
        bs,cs=scores(b),scores(c)
        differences.append(tuple(z-x for x,z in zip(bs,cs)))
    return {"n":len(rows),"mean_challenger_minus_baseline":{
        k:fsum(d[i] for d in differences)/len(rows)
        for i,k in enumerate(("log_loss","brier","rps"))},
        "timestamp_assertions_only":True,"confidence_interval_verified":False,
        "out_of_sample_verified":False,"deployment":"HOLD","recommendations":"DISABLED"}
