"""Offline score-state CTMC challenger, using Poisson uniformization.
Explicit hypothetical rates; cards fixed at snapshot; no fitted parameters.
"""
from collections import defaultdict
from math import exp, fsum
from ops.live_state_rate_scenarios_20261127 import remaining_rates
from ops.live_score_challenger_20261127 import summarize

TAIL_TOL=1e-12
MAX_TICKS=100

def transition_grid(score, red_cards, remaining_seconds, baseline_per90, *,
                    own_red_log, opponent_red_log, trailing_log, leading_log):
    coeff=dict(own_red_log=own_red_log,opponent_red_log=opponent_red_log,
               trailing_log=trailing_log,leading_log=leading_log)
    # Use three score signs to bound integrated rates for every reachable state.
    rates={}
    for sign,representative in [(-1,(0,1)),(0,(0,0)),(1,(1,0))]:
        rates[sign]=remaining_rates(representative,red_cards,remaining_seconds,
                                    baseline_per90,**coeff)
    remaining_rates(score,red_cards,remaining_seconds,baseline_per90,**coeff)
    start=tuple(score)
    q=max(fsum(v) for v in rates.values())
    if q==0:
        return {start:1.0},0.0,0
    if q>24:
        raise ValueError("uniformization intensity outside supported range")
    # q is integrated dominating intensity over the supplied remaining time.
    # At each virtual event, either score changes or a self-transition occurs.
    current={start:1.0}
    weight=exp(-q)
    weights=[weight]
    result=defaultdict(float,{start:weight})
    for k in range(1,MAX_TICKS+1):
        nxt=defaultdict(float)
        for (h,a),p in current.items():
            if p==0:
                continue
            sign=(h>a)-(h<a)
            rh,ra=rates[sign]
            ph,pa=rh/q,ra/q
            stay=max(0.0,1-ph-pa)
            if ph: nxt[h+1,a]+=p*ph
            if pa: nxt[h,a+1]+=p*pa
            if stay: nxt[h,a]+=p*stay
        current=nxt
        weight*=q/k
        weights.append(weight)
        for s,p in current.items():
            result[s]+=weight*p
        # Geometric upper bound on remaining Poisson tail once terms decrease.
        if k+2>q:
            bound=(weight*q/(k+1))/(1-q/(k+2))
            if bound<=TAIL_TOL:
                mass=fsum(result.values())
                if abs(mass-fsum(weights))>1e-10 or mass<=0:
                    raise ArithmeticError("transition probability drift")
                return {s:p/mass for s,p in result.items()},bound,k
    raise ArithmeticError("Poisson tail bound not reached")

def transition_scenario(score,red_cards,remaining_seconds,baseline_per90,**coeff):
    grid,tail,ticks=transition_grid(score,red_cards,remaining_seconds,baseline_per90,**coeff)
    out=summarize(grid)
    h,d,a=out["one_x_two"]
    side="home" if score[0]<score[1] else "away" if score[1]<score[0] else None
    out.update(trailing_side=side,
               trailing_side_final_win=h if side=="home" else a if side=="away" else None,
               trailing_side_avoid_defeat=h+d if side=="home" else a+d if side=="away" else None,
               expected_final_goals=fsum((i+j)*p for (i,j),p in grid.items()),
               poisson_tail_upper_bound=tail,uniformization_ticks=ticks,
               rate_model="score_sign_ctmc_hypothesis",future_cards_simulated=False,
               live_xg_verified=False,red_card_calibrated=False,qualified=False,
               deployment="HOLD",recommendations="DISABLED")
    return out
