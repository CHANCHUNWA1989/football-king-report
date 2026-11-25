"""Research-only prequential 1X2 ensemble, no market or production selector.

Weights use only earlier same-league settled forecasts as declared by input.
No claim of source/time authentication, fresh OOS advantage or coherent
scoreline/Asian market probabilities. Fixed parameters are not fitted.
"""
from collections import defaultdict
from math import exp, fsum, isfinite, log
from ops.expanding_walkforward_audit import _utc
from ops.offline_1x2_validation import OUTCOMES, evaluate_1x2

MODELS = ("original_A", "poisson", "dixon_coles", "dynamic_score_poisson")
MIN_HISTORY = 30
SHRINK = 20
ETA = 2.0
UNIFORM_MIX = .20
MAX_ROWS = 5000
KEYS = {"event_id", "league", "forecast_at", "kickoff_at",
        "settled_at", "outcome", "model_probabilities"}


def _hold(reason):
    return {"status":"HOLD", "reason":reason,
            "production_recommendations":"DISABLED",
            "model_promoted":False, "production_weights_changed":False,
            "positive_ev_verified":False, "certified_prospective_samples":0,
            "source_times_authenticated":False, "scoreline_coherence_verified":False}


def _name(x):
    if type(x) is not str or not x.strip() or x != x.strip() or len(x)>128:
        raise ValueError("INVALID_ID")
    return x


def _validate(rows):
    if type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS:
        raise ValueError("INVALID_COHORT")
    seen=set()
    valid=[]
    for row in rows:
        if type(row) is not dict or set(row)!=KEYS:
            raise ValueError("INVALID_ROW")
        event, league = _name(row["event_id"]), _name(row["league"])
        if event in seen:
            raise ValueError("DUPLICATE_EVENT")
        seen.add(event)
        f,k,s=(_utc(row[t]) for t in ("forecast_at","kickoff_at","settled_at"))
        if not f<k<s or row["outcome"] not in OUTCOMES:
            raise ValueError("INVALID_CHRONOLOGY_OR_OUTCOME")
        probs=row["model_probabilities"]
        if type(probs) is not dict or set(probs)!=set(MODELS):
            raise ValueError("INCOMPLETE_MODEL_COHORT")
        for model in MODELS:
            v=probs[model]
            if (type(v) is not dict or set(v)!=set(OUTCOMES)
                    or any(type(x) not in (int,float) or not isfinite(x)
                           or not 0<=x<=1 for x in v.values())
                    or abs(fsum(v.values())-1)>1e-8):
                raise ValueError("INVALID_PROBABILITY")
        valid.append((f,k,s,event,league,row))
    return valid


def _weights(n, losses):
    if n<MIN_HISTORY:
        return {m:1/len(MODELS) for m in MODELS}
    # Shrink the relative mean log losses toward a common prior.
    effective={m:losses[m]/(n+SHRINK) for m in MODELS}
    best=min(effective.values())
    raw={m:exp(-ETA*(effective[m]-best)) for m in MODELS}
    denom=fsum(raw.values())
    return {m:UNIFORM_MIX/len(MODELS)+(1-UNIFORM_MIX)*raw[m]/denom for m in MODELS}


def _mix(probs,weights):
    return {y:fsum(weights[m]*probs[m][y] for m in MODELS) for y in OUTCOMES}


def evaluate(rows):
    try:
        valid=_validate(rows)
        by_result=sorted(valid,key=lambda v:(v[2],v[3]))
        by_forecast=sorted(valid,key=lambda v:(v[0],v[3]))
        counts=defaultdict(int)
        losses=defaultdict(lambda:{m:0. for m in MODELS})
        cursor=0
        comparisons={m:[] for m in (*MODELS,"uniform","adaptive")}
        trace=[]
        for f,k,s,event,league,row in by_forecast:
            while cursor<len(by_result) and by_result[cursor][2]<f:
                _,_,_,_,prior_league,prior=by_result[cursor]
                counts[prior_league]+=1
                for m in MODELS:
                    losses[prior_league][m]-=log(max(
                        prior["model_probabilities"][m][prior["outcome"]],1e-15))
                cursor+=1
            n=counts[league]
            w=_weights(n,losses[league])
            probs=row["model_probabilities"]
            uniform={m:1/len(MODELS) for m in MODELS}
            vectors={**probs,"uniform":_mix(probs,uniform),"adaptive":_mix(probs,w)}
            trace.append({"event_id":event,"league":league,"prior_count":n,
                          "weights":w,"adaptive_active":n>=MIN_HISTORY})
            for m,v in vectors.items():
                comparisons[m].append({"event_id":event,"probabilities":v,
                                       "outcome":row["outcome"]})
        return {**_hold("DECLARED_CHRONOLOGY_RESEARCH_ONLY"),
                "paired_n":len(valid),"adaptive_active_n":sum(t["adaptive_active"] for t in trace),
                "fixed_research_parameters":{"min_history":MIN_HISTORY,"shrink":SHRINK,
                    "eta":ETA,"uniform_mix":UNIFORM_MIX},
                "diagnostics":{m:evaluate_1x2(v) for m,v in comparisons.items()},
                "weight_trace":trace}
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError):
        return _hold("INVALID_OR_INCOMPLETE_COHORT")
