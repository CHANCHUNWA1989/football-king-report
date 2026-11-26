"""Fixed three-model retrospective Liga MX comparison; never promote.
All models share prior-date-only history and identical assessment fixtures.
No odds, xG, red cards, independently witnessed forecast or production credit.
"""
import json
import math
from collections import defaultdict
from itertools import groupby
from live_core_multi_source import fetch_openfootball,openfootball,unique
from score_distribution_vnext import score_matrix,one_x_two

MODELS=("league_poisson","team_poisson","team_dc")
OUTCOMES=("HOME","DRAW","AWAY")
PRIOR=8
RHO=-.08
WARMUP=50


def clip(v):
    return max(.1,min(5.5,v))


def compare(rows):
    rows=unique(rows)
    hist=defaultdict(lambda:[0,0,0,0,0,0])
    n=gh=ga=0
    metrics={k:{"loss":[],"brier":[],"correct":0} for k in MODELS}
    for _,group in groupby(rows,key=lambda r:r[0]):
        batch=list(group)
        if n>=WARMUP:
            H,A=clip(gh/n),clip(ga/n)
            for _,home,away,x,y in batch:
                h,a=hist[home],hist[away]
                hr=clip(((h[1]+PRIOR*H)/(h[0]+PRIOR))*((a[5]+PRIOR*H)/(a[3]+PRIOR))/H)
                ar=clip(((a[4]+PRIOR*A)/(a[3]+PRIOR))*((h[2]+PRIOR*A)/(h[0]+PRIOR))/A)
                outcome="HOME" if x>y else "DRAW" if x==y else "AWAY"
                for name,(u,v,rho) in zip(MODELS,((H,A,0),(hr,ar,0),(hr,ar,RHO))):
                    p=one_x_two(score_matrix(u,v,rho=rho))
                    z=metrics[name]
                    z["loss"].append(-math.log(max(1e-15,p[outcome])))
                    z["brier"].append(math.fsum((p[k]-(k==outcome))**2 for k in OUTCOMES))
                    z["correct"]+=max(OUTCOMES,key=lambda k:p[k])==outcome
        for _,home,away,x,y in batch:
            h,a=hist[home],hist[away]
            h[0]+=1;h[1]+=x;h[2]+=y
            a[3]+=1;a[4]+=y;a[5]+=x
            n+=1;gh+=x;ga+=y
    result={}
    for name,z in metrics.items():
        k=len(z["loss"])
        result[name]={"n":k,"log_loss":math.fsum(z["loss"])/k if k else None,
            "brier":math.fsum(z["brier"])/k if k else None,
            "accuracy":z["correct"]/k if k else None}
    return {"models":result,"finished_matches":n,"teams":len(hist),
            "warmup_minimum":WARMUP,"venue_prior_matches":PRIOR,"fixed_rho":RHO,
            "historically_reconstructed":True,"assessment_previously_inspected":True,
            "model_calibrated":False,"automatic_promotion":False,
            "verified_forward_sample_credit":0,"positive_ev_verified":False,
            "production_recommendations":"DISABLED","status":"HOLD"}


if __name__=="__main__":
    print(json.dumps(compare(openfootball(fetch_openfootball())),sort_keys=True,allow_nan=False))
