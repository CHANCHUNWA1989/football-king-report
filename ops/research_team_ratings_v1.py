"""Research-only per-team attack/defence online ratings.

Chronological pre-match predictions only; no data feeds, fitted parameters,
bookmaker quotes, claimed out-of-sample uplift, or production execution.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence
from ops.research_multimodel_v1 import probabilities, score_matrix, multiclass_brier, log_loss

@dataclass(frozen=True)
class Fixture:
    kickoff: datetime
    home: str
    away: str
    home_goals: int
    away_goals: int
    verified: bool

def _bounded(x: float, limit: float=1.0) -> float:
    return min(limit,max(-limit,x))

def _validate(fixtures: Sequence[Fixture]) -> None:
    last=None
    for f in fixtures:
        if f.kickoff.tzinfo is None or f.kickoff.utcoffset() is None:
            raise ValueError("timezone-aware kickoff required")
        if last is not None and f.kickoff <= last:
            raise ValueError("chronological order required")
        last=f.kickoff
        if not f.verified or not f.home.strip() or not f.away.strip() or f.home==f.away:
            raise ValueError("invalid or unverified fixture")
        if any(type(v) is not int or v<0 or v>20 for v in (f.home_goals,f.away_goals)):
            raise ValueError("invalid observed goals")

def walk_forward_teams(fixtures: Sequence[Fixture], *, warmup: int=30,
                       learning_rate: float=0.04, decay: float=0.995) -> dict:
    _validate(fixtures)
    if type(warmup) is not int or warmup<1 or len(fixtures)<=warmup:
        raise ValueError("insufficient observations")
    if not (math.isfinite(learning_rate) and 0<learning_rate<=0.2 and
            math.isfinite(decay) and 0<=decay<=1):
        raise ValueError("invalid research hyperparameters")
    states: dict[str,tuple[float,float]]={}
    losses={"baseline_brier":[],"challenger_brier":[],
            "baseline_log_loss":[],"challenger_log_loss":[]}
    baseline=probabilities(score_matrix(1.4,1.1))
    for idx,f in enumerate(fixtures):
        ha,hd=states.get(f.home,(0.,0.))
        aa,ad=states.get(f.away,(0.,0.))
        lh=1.4*math.exp(_bounded(ha-ad))
        la=1.1*math.exp(_bounded(aa-hd))
        challenger=probabilities(score_matrix(lh,la))
        outcome="home" if f.home_goals>f.away_goals else ("away" if f.home_goals<f.away_goals else "draw")
        if idx>=warmup:
            for name,p in (("baseline",baseline),("challenger",challenger)):
                losses[name+"_brier"].append(multiclass_brier(p,outcome))
                losses[name+"_log_loss"].append(log_loss(p,outcome))
        # Update only AFTER this match has been scored. No future outcomes enter prediction.
        err_h=_bounded(f.home_goals-lh,3.)
        err_a=_bounded(f.away_goals-la,3.)
        states[f.home]=(_bounded(decay*ha+learning_rate*err_h),
                        _bounded(decay*hd-learning_rate*err_a))
        states[f.away]=(_bounded(decay*aa+learning_rate*err_a),
                        _bounded(decay*ad-learning_rate*err_h))
    return {"status":"RESEARCH_ONLY","production_recommendations":"DISABLED",
            "qualified_for_production":False,"n_test":len(fixtures)-warmup,
            "teams_seen":len(states),"metrics":{k:sum(v)/len(v) for k,v in losses.items()},
            "verified_chronology":True,"team_specific_model":True}
