"""Research-only unified Asian handicap / totals settlement from score matrix.

All odds decimal; all line values from home-team perspective for handicap.
No market feeds, no executable quotes, no production promotion.
"""
from __future__ import annotations
import math
from typing import Sequence

def _quarter_line(line: float) -> tuple[float,...]:
    if isinstance(line,bool) or not isinstance(line,(float,int)) or not math.isfinite(line):
        raise ValueError("invalid Asian line")
    scaled=round(line*4)
    if abs(line*4-scaled)>1e-9 or abs(line)>20:
        raise ValueError("line must be a quarter goal increment")
    if scaled%2:
        return ((scaled-1)/4,(scaled+1)/4)
    return (scaled/4,)

def _matrix(matrix: Sequence[Sequence[float]]) -> None:
    if not matrix or any(len(row)!=len(matrix) for row in matrix):
        raise ValueError("square score matrix required")
    vals=[p for row in matrix for p in row]
    if any(not isinstance(p,(int,float)) or not math.isfinite(p) or p<0 for p in vals):
        raise ValueError("invalid score probability")
    if abs(sum(vals)-1)>1e-8:
        raise ValueError("score probabilities must sum to one")

def _settle(value: float) -> int:
    if value>1e-10:return 1
    if value< -1e-10:return -1
    return 0

def asian_ev(matrix: Sequence[Sequence[float]], *, market: str,
             selection: str, line: float, decimal_odds: float) -> dict:
    """EV net return per unit stake including push and half-win/half-loss.

    handicap: home or away, line always handicap applied to home goals.
    totals: over or under, line applied to total goals.
    """
    _matrix(matrix)
    if isinstance(decimal_odds,bool) or not isinstance(decimal_odds,(int,float)) or not math.isfinite(decimal_odds) or decimal_odds<=1:
        raise ValueError("decimal odds must exceed 1")
    if (market=="handicap" and selection not in ("home","away")) or (
        market=="totals" and selection not in ("over","under")) or market not in ("handicap","totals"):
        raise ValueError("invalid market selection")
    lines=_quarter_line(line)
    buckets={"full_win":0.,"half_win":0.,"push":0.,"half_loss":0.,"full_loss":0.}
    ev=0.
    for h,row in enumerate(matrix):
        for a,p in enumerate(row):
            outcomes=[]
            for part in lines:
                if market=="handicap":
                    margin=h-a+part
                    outcomes.append(_settle(margin if selection=="home" else -margin))
                else:
                    margin=h+a-part
                    outcomes.append(_settle(margin if selection=="over" else -margin))
            net=sum(decimal_odds-1 if v==1 else (-1 if v==-1 else 0) for v in outcomes)/len(outcomes)
            ev+=p*net
            score=sum(outcomes)/len(outcomes)
            key={1:"full_win",0.5:"half_win",0:"push",-0.5:"half_loss",-1:"full_loss"}[score]
            buckets[key]+=p
    return {"status":"RESEARCH_ONLY","production_recommendations":"DISABLED",
            "market":market,"selection":selection,"line":float(line),
            "decimal_odds":float(decimal_odds),"expected_net_return":ev,
            "outcome_probabilities":buckets,
            "executable_quote_verified":False,"qualified_for_production":False}
