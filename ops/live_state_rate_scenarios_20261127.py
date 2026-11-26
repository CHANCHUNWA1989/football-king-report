"""Research-only snapshot-conditioned goal-rate sensitivity.
No live feed, no fitted coefficients, no production recommendations.
Rates are held fixed between snapshots; future cards and tactical changes are not simulated.
"""
from math import exp, fsum
from ops.live_score_challenger_20261127 import number, score_grid, summarize

def _pair(x, low, high, integer=False):
    if not isinstance(x,(list,tuple)) or len(x)!=2 or any(
        (type(v) is not int if integer else not number(v)) or not low<=v<=high
        for v in x):
        raise ValueError("invalid pair")
    return tuple(x)

def remaining_rates(score, red_cards, remaining_seconds, baseline_per90, *,
                    own_red_log, opponent_red_log, trailing_log, leading_log):
    """Caller explicitly supplies scenario coefficients; no default fitted values.
    Baseline is neutral-state per-90 expected scoring intensity, not odds or cumulative xG.
    Remaining seconds is explicit estimated playing time, excluding halftime.
    Score modifiers depend on current sign, not margin size.
    """
    h,a=_pair(score,0,30,True)
    rh,ra=_pair(red_cards,0,4,True)
    bh,ba=_pair(baseline_per90,0,6)
    if not number(remaining_seconds) or not 0<=remaining_seconds<=7200:
        raise ValueError("invalid remaining playing time")
    for v,lo,hi in ((own_red_log,-1,0),(opponent_red_log,0,1),
                    (trailing_log,0,.5),(leading_log,-.5,0)):
        if not number(v) or not lo<=v<=hi:
            raise ValueError("scenario coefficient outside research bounds")
    scale=remaining_seconds/5400
    hs=trailing_log if h<a else leading_log if h>a else 0
    aas=trailing_log if a<h else leading_log if a>h else 0
    # Equal dismissals cancel only when own and opponent coefficients offset.
    hm=bh*scale*exp(rh*own_red_log+ra*opponent_red_log+hs)
    am=ba*scale*exp(ra*own_red_log+rh*opponent_red_log+aas)
    if max(hm,am)>12:
        raise ValueError("scenario exceeds supported score-grid range")
    return hm,am

def scenario(score, red_cards, remaining_seconds, baseline_per90, *,
             own_red_log, opponent_red_log, trailing_log, leading_log, rho=0):
    means=remaining_rates(score,red_cards,remaining_seconds,baseline_per90,
                          own_red_log=own_red_log,opponent_red_log=opponent_red_log,
                          trailing_log=trailing_log,leading_log=leading_log)
    grid=score_grid(score,*means,rho)
    out=summarize(grid)
    h,d,a=out["one_x_two"]
    # Full-time victory from CURRENT trailing state, not pathwise comeback.
    trailing_side="home" if score[0]<score[1] else "away" if score[1]<score[0] else None
    out.update(remaining_goal_means=means,trailing_side=trailing_side,
               trailing_side_final_win=h if trailing_side=="home" else a if trailing_side=="away" else None,
               trailing_side_avoid_defeat=h+d if trailing_side=="home" else a+d if trailing_side=="away" else None,
               expected_final_goals=fsum((i+j)*p for (i,j),p in grid.items()),
               rate_model="fixed_between_snapshots_hypothesis",
               live_xg_verified=False,red_card_calibrated=False,
               deployment="HOLD",recommendations="DISABLED",qualified=False)
    return out

def sensitivity(score,red_cards,remaining_seconds,baseline_per90,parameter_sets):
    """Range across supplied scenarios, not a statistical confidence interval."""
    if not isinstance(parameter_sets,list) or not 1<=len(parameter_sets)<=32:
        raise ValueError("provide 1 to 32 explicit scenarios")
    results=[scenario(score,red_cards,remaining_seconds,baseline_per90,**p)
             for p in parameter_sets]
    return {"scenario_count":len(results),
            "one_x_two_ranges":[[min(r["one_x_two"][i] for r in results),
                                 max(r["one_x_two"][i] for r in results)] for i in range(3)],
            "range_is_confidence_interval":False,"fitted":False,
            "positive_ev_verified":False,"deployment":"HOLD","recommendations":"DISABLED"}
