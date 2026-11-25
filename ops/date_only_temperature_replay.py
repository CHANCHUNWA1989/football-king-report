"""Date-only retrospective temperature pilot. Never authenticates source times.

Fixed early 75% fitting / last 25% validation, with two calendar day embargo.
Uses original frozen 2025-trained 1X2 vectors on the reused 2026 cohort.
No temperature applied to production or other market marginals.
"""
from datetime import date
from math import fsum, isfinite
from ops.prospective_temperature_challenger import TEMPERATURES, _temperature, _loss, _probabilities

MODELS=("original_A","poisson","dixon_coles","dynamic_score_poisson")
CLASSES=("HOME","DRAW","AWAY")


def evaluate(days,vectors,outcomes):
    n=len(days)
    if (not 1<=n<=5000 or len(outcomes)!=n or set(vectors)!=set(MODELS)
            or any(len(vectors[m])!=n for m in MODELS)):
        raise ValueError("INVALID_CALIBRATION_COHORT")
    parsed=[date.fromisoformat(d) for d in days]
    if any(d.isoformat()!=raw for d,raw in zip(parsed,days)):
        raise ValueError("INVALID_DATE")
    for i,y in enumerate(outcomes):
        if y not in CLASSES:
            raise ValueError("INVALID_OUTCOME")
    clean={}
    for m in MODELS:
        clean[m]=[]
        for i,p in enumerate(vectors[m]):
            if type(p) is not dict or set(p)!=set(CLASSES):
                raise ValueError("INVALID_CALIBRATION_PROBABILITY")
            clean[m].append({"p":_probabilities([p[k] for k in CLASSES]),
                             "y":CLASSES.index(outcomes[i])})
    boundary=sorted(parsed)[n-max(1,n//4)]
    train=[i for i,d in enumerate(parsed) if (boundary-d).days>=2]
    test=[i for i,d in enumerate(parsed) if d>=boundary]
    out={"status":"HOLD","production_recommendations":"DISABLED",
         "model_promoted":False,"certified_prospective_samples":0,
         "production_weights_changed":False,"positive_ev_verified":False,
         "reused_historical_cohort":True,"date_only_proxy_not_actual_result_availability":True,
         "fit_n":len(train),"validation_n":len(test),"embargo_excluded_n":n-len(train)-len(test),
         "validation_start_date":boundary.isoformat(),"model_reports":{}}
    if len(train)<90 or len(test)<30:
        return {**out,"reason":"INSUFFICIENT_CALIBRATION_SPLIT"}
    for m in MODELS:
        early=[clean[m][i] for i in train]
        late=[clean[m][i] for i in test]
        t=min(TEMPERATURES,key=lambda t:(_loss(early,t)["log_loss"],t))
        base=_loss(late,1.)
        candidate=_loss(late,t)
        improved=t>1 and all(candidate[k]<base[k]-1e-5 for k in base)
        out["model_reports"][m]={"temperature_fit_only":t,"validation_baseline":base,
                                 "validation_candidate":candidate,
                                 "research_both_metrics_improved":improved}
    return {**out,"reason":"RETROSPECTIVE_CALIBRATION_DIAGNOSTIC_ONLY"}
