"""Paired descriptive attribution of fixed V35 predictions. No refitting."""
from collections import defaultdict
from math import log,isfinite
from random import Random

DRAWS=2000
def losses(p,y):
    if (not isinstance(p,list) or len(p)!=3 or any(type(v) not in (int,float) or not isfinite(v) or not 0<=v<=1 for v in p)
        or abs(sum(p)-1)>1e-8 or type(y) is not int or not 0<=y<=2):
        raise ValueError("invalid paired probability")
    return -log(max(p[y],1e-15)),sum((v-int(i==y))**2 for i,v in enumerate(p))

def summarize(rows):
    n=len(rows)
    if not n:return {"n":0,"log_loss_delta":None,"brier_delta":None,"expanded_vs_market_log_loss_delta":None,
                    "interval":{"status":"INSUFFICIENT_SAMPLE","lower":None,"upper":None}}
    days=defaultdict(list)
    dl=[];db=[];dm=[]
    for r in rows:
        a,b=losses(r["original"],r["y"]);c,d=losses(r["expanded"],r["y"]);m,_=losses(r["market"],r["y"])
        dl.append(c-a);db.append(d-b);dm.append(c-m)
        days[r["forecast_day"]].append(c-a)
    interval={"status":"INSUFFICIENT_SAMPLE","lower":None,"upper":None}
    if n>=30 and len(days)>=10:
        groups=[days[d] for d in sorted(days)]
        rng=Random(36);draws=[]
        for _ in range(DRAWS):
            selected=rng.choices(groups,k=len(groups))
            draws.append(sum(sum(x) for x in selected)/sum(len(x) for x in selected))
        draws.sort()
        interval={"status":"DESCRIPTIVE_CLUSTER_BOOTSTRAP","lower":draws[int(.025*DRAWS)],
                  "upper":draws[int(.975*DRAWS)-1],"draws":DRAWS}
    return {"n":n,"forecast_days":len(days),"log_loss_delta":sum(dl)/n,"brier_delta":sum(db)/n,
            "expanded_vs_market_log_loss_delta":sum(dm)/n,
            "worse_log_loss_cases":sum(x>1e-12 for x in dl),"better_log_loss_cases":sum(x< -1e-12 for x in dl),
            "interval":interval}

def attribute(rows):
    groups=defaultdict(list);support=defaultdict(list)
    for r in rows:
        n=r["extra_league_prior"]
        if type(n) is not int or n<0:raise ValueError("invalid supplemental support")
        if type(r["strict"]) is not bool:raise ValueError("invalid strict cohort")
        if n==0 and any(abs(a-b)>1e-12 for a,b in zip(r["original"],r["expanded"])):
            raise ValueError("zero league support cannot change predictions")
        groups[r["league"]].append(r)
        support["zero" if n==0 else "one_to_four" if n<=4 else "five_plus"].append(r)
    return {"delay_hours":24,"all":summarize(rows),"strict":summarize([r for r in rows if r["strict"]]),
            "by_league":{k:summarize(v) for k,v in sorted(groups.items())},
            "by_extra_league_support":{k:summarize(support[k]) for k in ("zero","one_to_four","five_plus")},
            "delta_definition":"expanded minus original; positive is worse",
            "descriptive_only":True,"selection_bias_possible":True,"no_parameter_selection":True}
