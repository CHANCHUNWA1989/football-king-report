"""Date-only retrospective fusion of the four frozen 2025-trained 1X2 models.

Two calendar-day separation is a proxy, NOT a genuine availability timestamp.
All forecasts are generated retrospectively on a previously inspected cohort.
No league transfer, authentic prospective evidence, odds or model promotion.
"""
from datetime import date
from math import fsum, isfinite, log
from ops.adaptive_league_ensemble_research import MODELS, MIN_HISTORY, _weights
from ops.offline_1x2_validation import OUTCOMES, evaluate_1x2

CLASSES = ("HOME","DRAW","AWAY")
GAP_DAYS = 2


def evaluate_date_fusion(days, vectors, outcomes):
    n=len(days)
    if (not 1<=n<=5000 or len(outcomes)!=n or set(vectors)!=set(MODELS)
            or any(len(vectors[m])!=n for m in MODELS)):
        raise ValueError("INVALID_FUSION_COHORT")
    parsed=[date.fromisoformat(d) for d in days]
    if any(d.isoformat()!=raw for d,raw in zip(parsed,days)):
        raise ValueError("INVALID_DATE")
    for i in range(n):
        if outcomes[i] not in CLASSES:
            raise ValueError("INVALID_OUTCOME")
        for m in MODELS:
            p=vectors[m][i]
            if (set(p)!=set(CLASSES) or any(type(x) not in (int,float)
                    or not isfinite(x) or not 0<=x<=1 for x in p.values())
                    or abs(fsum(p.values())-1)>1e-6):
                raise ValueError("INVALID_FUSION_PROBABILITY")
    order=sorted(range(n),key=lambda i:(parsed[i],i))
    counts=0
    losses={m:0. for m in MODELS}
    cursor=0
    all_rows={m:[] for m in (*MODELS,"uniform","adaptive")}
    active_rows={m:[] for m in all_rows}
    trace=[]
    for i in order:
        while cursor<n and (parsed[i]-parsed[order[cursor]]).days>=GAP_DAYS:
            j=order[cursor]
            for m in MODELS:
                losses[m]-=log(max(vectors[m][j][outcomes[j]],1e-15))
            counts+=1
            cursor+=1
        w=_weights(counts,losses)
        forecasts={m:vectors[m][i] for m in MODELS}
        forecasts["uniform"]={y:fsum(vectors[m][i][y] for m in MODELS)/len(MODELS)
                              for y in CLASSES}
        forecasts["adaptive"]={y:fsum(w[m]*vectors[m][i][y] for m in MODELS)
                               for y in CLASSES}
        trace.append({"row_index":i,"date":days[i],"prior_count":counts,"weights":w})
        for m,p in forecasts.items():
            # Tiny floating point mass residual is normalized for the scoring helper.
            mass=fsum(p.values())
            row={"event_id":str(i),"probabilities":{k:p[y]/mass
                  for k,y in zip(OUTCOMES,CLASSES)},
                 "outcome":OUTCOMES[CLASSES.index(outcomes[i])]}
            all_rows[m].append(row)
            if counts>=MIN_HISTORY:
                active_rows[m].append(row)
    active_n=len(active_rows["adaptive"])
    return {"status":"HOLD","production_recommendations":"DISABLED",
            "certified_prospective_samples":0,"model_promoted":False,
            "positive_ev_verified":False,"production_weights_changed":False,
            "date_only_proxy_not_actual_result_availability":True,
            "reused_historical_cohort":True,"minimum_date_gap_days":GAP_DAYS,
            "paired_n":n,"adaptive_active_n":active_n,
            "all_cohort":{m:evaluate_1x2(rows) for m,rows in all_rows.items()},
            "active_cohort":{m:evaluate_1x2(rows) for m,rows in active_rows.items()}
                            if active_n else None,
            "weight_trace":trace}
