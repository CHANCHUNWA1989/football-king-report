"""Research-only convex mixture of common exact-score grids.

This pilot uses the two fixed-rho numerical candidates on a common 0..24
support. It is not a mixture of the fitted historical four-model forecasts.
No 14+ collapsed bucket, inferred joint PMF from 1X2, odds, or promotion.
"""
import math
from ops.core_unified_score_grid import (
    score_grid, one_x_two, asian_handicap, totals, three_way_handicap,
    MAX_GOALS, RHO, GRADES,
)

MODELS = ("poisson_rho_zero", "fixed_dc")
AH_LINES = (-2.,-1.75,-1.5,-1.25,-1.,-.75,-.5,-.25,0.,.25,.5,.75,1.,1.25,1.5,1.75,2.)
TOTAL_LINES = (1.5,2.,2.25,2.5,2.75,3.,3.25,3.5,4.)
OPPOSITE = dict(zip(GRADES,reversed(GRADES)))


def _weight(v):
    return type(v) in (int,float) and math.isfinite(v) and 0<=v<=1


def mix_scenarios(rates, weights):
    """One set of scenario weights for every market, not market-specific fits."""
    if (type(rates) is not dict or type(weights) is not dict
            or set(rates)!=set(MODELS) or set(weights)!=set(MODELS)
            or any(not _weight(v) for v in weights.values())
            or abs(math.fsum(weights.values())-1)>1e-12):
        raise ValueError("INVALID_SHARED_MODEL_WEIGHTS_OR_RATES")
    grids, tails = {}, {}
    for m,rho in zip(MODELS,(0.,RHO)):
        pair=rates[m]
        if type(pair) not in (list,tuple) or len(pair)!=2:
            raise ValueError("INVALID_RATE_PAIR")
        grids[m],tails[m]=score_grid(*pair,rho=rho)
    grid=tuple(tuple(math.fsum(weights[m]*grids[m][i][j] for m in MODELS)
                     for j in range(MAX_GOALS+1)) for i in range(MAX_GOALS+1))
    if abs(math.fsum(math.fsum(row) for row in grid)-1)>2e-12:
        raise ValueError("UNNORMALIZED_MIXTURE")
    return grid, math.fsum(weights[m]*tails[m]["combined_tail_upper_bound"] for m in MODELS)


def _complement(left,right):
    if any(abs(left[k]-right[OPPOSITE[k]])>2e-12 for k in GRADES):
        raise ValueError("OPPOSITE_CONTRACT_MISMATCH")


def analyze(rates,weights):
    grid,tail=mix_scenarios(rates,weights)
    ah,ou,three={},{},{}
    p=one_x_two(grid)
    for line in AH_LINES:
        h=asian_handicap(grid,side="HOME",line=line)
        a=asian_handicap(grid,side="AWAY",line=-line)
        _complement(h,a)
        ah[str(line)]={"home":h,"away_opposite_line":a}
    for line in TOTAL_LINES:
        o=totals(grid,side="OVER",line=line)
        u=totals(grid,side="UNDER",line=line)
        _complement(o,u)
        ou[str(line)]={"over":o,"under":u}
    for line in (-2,-1,1,2):
        three[str(line)]=three_way_handicap(grid,home_handicap=line)
    if abs(p["HOME"]-ah["0.0"]["home"]["FULL_WIN"])>2e-12 or abs(
            p["DRAW"]-ah["0.0"]["home"]["PUSH"])>2e-12:
        raise ValueError("1X2_AH_CONSISTENCY_FAILURE")
    if abs(three["-1"]["DRAW"]-ah["-1.0"]["home"]["PUSH"])>2e-12:
        raise ValueError("THREEWAY_AH_CONSISTENCY_FAILURE")
    return {"status":"HOLD","production_recommendations":"DISABLED",
            "model_promoted":False,"production_weights_changed":False,
            "positive_ev_verified":False,"certified_prospective_samples":0,
            "fitted_historical_models_used":False,"source_rates_authenticated":False,
            "model_probabilities_calibrated":False,
            "common_exact_score_support_0_to_24":True,
            "weights":dict(weights),"weighted_unmodeled_tail_bound":tail,
            "score_matrix":grid,"full_time_1x2":p,"asian_handicap":ah,
            "total_goals":ou,"three_way_handicap":three}
