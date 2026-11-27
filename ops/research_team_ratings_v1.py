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
from ops.research_result_clock import ResultClock, validate_result_clock, utc, ordered_batches

@dataclass(frozen=True)
class Fixture:
    kickoff: datetime
    home: str
    away: str
    home_goals: int
    away_goals: int
    verified: bool
    result_available_utc: datetime | None = None
    fixture_id: str | None = None

def _bounded(x: float, limit: float=1.0) -> float:
    return min(limit,max(-limit,x))

def _validate(fixtures: Sequence[Fixture]) -> None:
    last=None
    for f in fixtures:
        if f.kickoff.tzinfo is None or f.kickoff.utcoffset() is None:
            raise ValueError("timezone-aware kickoff required")
        k=utc(f.kickoff)
        if last is not None and k < last:
            raise ValueError("chronological order required")
        last=k
        validate_result_clock(f.kickoff,f.result_available_utc)
        if f.verified is not True or not f.home.strip() or not f.away.strip() or f.home==f.away:
            raise ValueError("invalid or unverified fixture")
        if any(type(v) is not int or v<0 or v>20 for v in (f.home_goals,f.away_goals)):
            raise ValueError("invalid observed goals")

def walk_forward_teams(fixtures: Sequence[Fixture], *, warmup: int=30,
                       learning_rate: float=0.04, decay: float=0.995) -> dict:
    _validate(fixtures)
    requested_warmup=warmup
    fixtures,warmup,groups=ordered_batches(fixtures,lambda f:f.kickoff,warmup,teams=lambda f:(f.home,f.away))
    if not (math.isfinite(learning_rate) and 0<learning_rate<=0.2 and
            math.isfinite(decay) and 0<=decay<=1):
        raise ValueError("invalid research hyperparameters")
    states: dict[str,tuple[float,float]]={}
    losses={"baseline_brier":[],"challenger_brier":[],
            "baseline_log_loss":[],"challenger_log_loss":[]}
    baseline=probabilities(score_matrix(1.4,1.1))
    clock=ResultClock()
    seen=set()
    def apply(payload):
        f,lh,la=payload
        ha,hd=states.get(f.home,(0.,0.))
        aa,ad=states.get(f.away,(0.,0.))
        err_h=_bounded(f.home_goals-lh,3.)
        err_a=_bounded(f.away_goals-la,3.)
        states[f.home]=(_bounded(decay*ha+learning_rate*err_h),
                        _bounded(decay*hd-learning_rate*err_a))
        states[f.away]=(_bounded(decay*aa+learning_rate*err_a),
                        _bounded(decay*ad-learning_rate*err_h))
    for idx,f in enumerate(fixtures):
        clock.drain_before(f.kickoff,apply)
        seen.update((f.home,f.away))
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
        # Freeze kickoff-time expected goals; apply to current state when result is available.
        clock.schedule(f.result_available_utc,(f,lh,la))
    return {"status":"RESEARCH_ONLY","production_recommendations":"DISABLED",
            "qualified_for_production":False,"n_test":len(fixtures)-warmup,
            "requested_warmup":requested_warmup,"effective_warmup":warmup,"kickoff_groups":groups,
            "teams_seen":len(seen),"metrics":{k:sum(v)/len(v) for k,v in losses.items()},
            "verified_chronology":True,"team_specific_model":True,
            "result_availability_enforced":True,"availability_source_authenticated":False,
            "results_applied_before_last_kickoff":clock.applied}
