"""Offline unified full-time market probabilities from one score distribution.

No observed prices, no calibrated model, no EV qualification. Asian markets
use FULL_MATCH score convention only, not rest-of-match settlement.
"""
from collections import defaultdict
from collections.abc import Mapping
from math import fsum
from ops.live_snapshot_market_audit_20261126 import legs
from ops.live_score_challenger_20261127 import number
from ops.live_score_transition_20261127 import transition_grid

OUTCOMES=("full_win","half_win","push","half_loss","full_loss")

def _distribution(grid):
    if not isinstance(grid,Mapping) or not grid:
        raise ValueError("nonempty score grid required")
    for score,p in grid.items():
        if (not isinstance(score,tuple) or len(score)!=2 or
            any(type(x) is not int or x<0 for x in score) or
            not number(p) or not 0<=p<=1):
            raise ValueError("invalid score probability")
    mass=fsum(grid.values())
    if abs(mass-1)>1e-10:
        raise ValueError("score mass must sum to one")
    return {k:v/mass for k,v in grid.items()}

def _histogram(grid,fn):
    groups=defaultdict(list)
    for score,p in grid.items():
        groups[fn(*score)].append(p)
    return {k:fsum(v) for k,v in groups.items()}

def _settle(hist,line):
    x,y=legs(line)
    groups={k:[] for k in OUTCOMES}
    for margin,p in hist.items():
        signs=((margin+x>0)-(margin+x<0),(margin+y>0)-(margin+y<0))
        net=sum(signs)
        groups[OUTCOMES[2-net]].append(p)
    return {k:fsum(v) for k,v in groups.items()}

def unified_markets(grid,handicap_lines,total_lines,*,scope):
    if scope!="FULL_MATCH":
        raise ValueError("explicit full-match settlement required")
    for lines in (handicap_lines,total_lines):
        if not isinstance(lines,(list,tuple)) or len(lines)>121:
            raise ValueError("invalid line list")
        for line in lines:
            legs(line)
        if len(set(lines))!=len(lines):
            raise ValueError("duplicate line")
    if any(x<0 for x in total_lines):
        raise ValueError("negative total")
    g=_distribution(grid)
    margin=_histogram(g,lambda h,a:h-a)
    total=_histogram(g,lambda h,a:h+a)
    reverse={-k:v for k,v in margin.items()}
    under={-k:v for k,v in total.items()}
    home=fsum(v for k,v in margin.items() if k>0)
    draw=margin.get(0,0.0)
    away=fsum(v for k,v in margin.items() if k<0)
    return {"scope":scope,"one_x_two":[home,draw,away],
            "handicaps":[{"home_line":x,"home":_settle(margin,x),
                          "away_line":-x,"away":_settle(reverse,-x)}
                         for x in handicap_lines],
            "totals":[{"line":x,"over":_settle(total,-x),"under":_settle(under,x)}
                      for x in total_lines],
            "both_teams_score":fsum(p for (h,a),p in g.items() if h>0 and a>0),
            "expected_final_goals":fsum(k*v for k,v in total.items()),
            "market_quotes_observed":False,"positive_ev_verified":False,
            "calibrated":False,"qualified":False,"deployment":"HOLD",
            "recommendations":"DISABLED"}

def transition_markets(score,red_cards,remaining_seconds,baseline_per90,*,
                       handicap_lines,total_lines,scope,**coeff):
    grid,tail,ticks=transition_grid(score,red_cards,remaining_seconds,baseline_per90,**coeff)
    result=unified_markets(grid,handicap_lines,total_lines,scope=scope)
    result.update(model="score_sign_ctmc_hypothesis",poisson_tail_upper_bound=tail,
                  uniformization_ticks=ticks,live_xg_verified=False)
    return result
