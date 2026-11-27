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
from ops.research_result_clock import ResultClock, validate_result_clock, utc, ordered_batches, prediction_cutoffs, whole_forecast_warmup, event_time_batches

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
    forecast_utc: datetime | None = None

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
                       learning_rate: float=0.04, decay: float=0.995,
                       require_explicit_forecast: bool=False, event_time_order: bool=False) -> dict:
    _validate(fixtures)
    requested_warmup=warmup
    if not (math.isfinite(learning_rate) and 0<learning_rate<=0.2 and
            math.isfinite(decay) and 0<=decay<=1):
        raise ValueError("invalid research hyperparameters")
    if type(event_time_order) is not bool or type(require_explicit_forecast) is not bool:
        raise ValueError("invalid replay flags")
    if event_time_order:
        fixtures,warmup,groups,cutoffs=event_time_batches(fixtures,lambda f:f.kickoff,warmup,teams=lambda f:(f.home,f.away))
        cutoff_mode="EXPLICIT_RECORDED_FORECAST"
        cutoff_for=lambda row:cutoffs[row.fixture_id]
    else:
        fixtures,warmup,groups=ordered_batches(fixtures,lambda f:f.kickoff,warmup,teams=lambda f:(f.home,f.away))
        cutoffs,cutoff_mode=prediction_cutoffs(fixtures,lambda f:f.kickoff,require_explicit=require_explicit_forecast)
        warmup=whole_forecast_warmup(fixtures,lambda f:f.kickoff,cutoffs,warmup)
        cutoff_for=lambda row:cutoffs[utc(row.kickoff)]
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
        clock.drain_before(cutoff_for(f),apply)
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
        # Freeze forecast-time expected goals; apply to current state when result is available.
        clock.schedule(f.result_available_utc,(f,lh,la))
    return {"status":"RESEARCH_ONLY","production_recommendations":"DISABLED",
            "qualified_for_production":False,"n_test":len(fixtures)-warmup,
            "requested_warmup":requested_warmup,"effective_warmup":warmup,"kickoff_groups":groups,
            "teams_seen":len(seen),"metrics":{k:sum(v)/len(v) for k,v in losses.items()},
            "verified_chronology":True,"team_specific_model":True,
            "result_availability_enforced":True,"availability_source_authenticated":False,
            "forecast_cutoff_mode":cutoff_mode,"forecast_clock_authenticated":False,
            "evaluation_order":"FORECAST_UTC" if event_time_order else "KICKOFF_UTC",
            "results_applied_before_last_forecast":clock.applied,
            "results_applied_before_last_kickoff":None if event_time_order else clock.applied}
