"""Frozen research policy for prospective validation; not deployed.

The retrospective comparison is descriptive only, with no outcome-driven
weight tuning or choice of a winning policy.
"""
import math
from collections import Counter,defaultdict
from .research_attack_defence_replay_v35 import metrics
from .research_replay_attribution_v36 import losses

POLICY="support-capped-market-fusion-v37"
CAP=.10
MAX_AGE_SECONDS=3600

def normalized(p):
    if (not isinstance(p,list) or len(p)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=1 for x in p)
        or abs(sum(p)-1)>.002):
        raise ValueError("invalid probability vector")
    return [x/sum(p) for x in p]

def mix(model,market,w):
    a,b=normalized(model),normalized(market)
    return [(1-w)*q+w*p for p,q in zip(a,b)]

def candidate(model,market,*,support,market_age_seconds):
    a,b=normalized(model),normalized(market)
    if (not isinstance(support,(tuple,list)) or len(support)!=4
        or any(type(n) is not int or n<0 for n in support)):
        raise ValueError("invalid support")
    total,league,home,away=support
    if not max(home,away)<=league<=total:
        raise ValueError("inconsistent support")
    if (type(market_age_seconds) not in (int,float) or not math.isfinite(market_age_seconds)
        or market_age_seconds<0):
        raise ValueError("invalid market clock")
    if market_age_seconds>MAX_AGE_SECONDS:
        return {"state":"STALE_MARKET_ABSTAIN","p":None,"weight":None}
    # Require both teams and league support. Fixed policy, independent of outcomes.
    w=CAP*min(1,league/20,home/5,away/5)
    return {"state":"RESEARCH_CANDIDATE","p":mix(a,b,w),"weight":w}

def evaluate(rows):
    pairs=defaultdict(list);counts=Counter();weights=[]
    for r in rows:
        result=candidate(r["expanded"],r["market"],support=r["expanded_support"],
                         market_age_seconds=r["market_age_seconds"])
        counts[result["state"]]+=1
        if result["p"] is None:continue
        y=r["y"]
        losses(result["p"],y)
        weights.append(result["weight"])
        for name,p in (("market",normalized(r["market"])),
                       ("expanded",normalized(r["expanded"])),
                       ("fixed_10pct",mix(r["expanded"],r["market"],CAP)),
                       ("adaptive_capped",result["p"])):
            pairs[name].append((p,y))
    return {"policy":POLICY,"max_model_weight":CAP,"market_age_limit_seconds":MAX_AGE_SECONDS,
            "target_count":len(rows),"states":dict(counts),"paired_count":len(weights),
            "mean_model_weight":sum(weights)/len(weights) if weights else None,
            "zero_weight_count":sum(w==0 for w in weights),
            "models":{name:metrics(pairs[name]) for name in ("market","expanded","fixed_10pct","adaptive_capped")},
            "historical_reconstruction_only":True,"metrics_descriptive_only":True,
            "market_same_cutoff_proven":False,"archive_timestamps_authenticated":False,
            "weights_fitted":False,"authenticated_samples":0,"independent_oos_proven":False,
            "production_recommendations":"DISABLED","model_promotion_allowed":False,"status":"HOLD"}
