"""Research-only leakage-resistant walk-forward comparison.

Input records must be historical, chronologically ordered and already verified.
No bookmaker execution, no automatic production promotion, no claimed uplift.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence
from ops.research_multimodel_v1 import score_matrix, probabilities, multiclass_brier, log_loss
from ops.research_gas_v1 import State, forecast, update
from ops.research_result_clock import ResultClock, validate_result_clock, utc, ordered_batches, prediction_cutoffs, whole_forecast_warmup, event_time_batches

@dataclass(frozen=True)
class Match:
    kickoff_utc: datetime
    home_goals: int
    away_goals: int
    source_verified: bool = False
    result_available_utc: datetime | None = None
    fixture_id: str | None = None
    forecast_utc: datetime | None = None

def _validate(matches: Sequence[Match]) -> None:
    previous = None
    for match in matches:
        if match.kickoff_utc.tzinfo is None or match.kickoff_utc.utcoffset() is None:
            raise ValueError("timezone-aware kickoff required")
        validate_result_clock(match.kickoff_utc,match.result_available_utc)
        if match.source_verified is not True:
            raise ValueError("unverified history prohibited")
        k=utc(match.kickoff_utc)
        if previous is not None and k < previous:
            raise ValueError("history must be chronological")
        previous = k
        if any(isinstance(v,bool) or not isinstance(v,int) or not 0<=v<=20
               for v in (match.home_goals,match.away_goals)):
            raise ValueError("invalid goals")

def walk_forward(matches: Sequence[Match], *, warmup: int=30, require_explicit_forecast: bool=False, event_time_order: bool=False) -> dict:
    """Prequential evaluation; forecast BEFORE observing each match result.

    Deliberately simplified aggregate state: NOT team-specific, NOT fitted GAS.
    This framework is an integration test, not evidence of forecasting uplift.
    """
    _validate(matches)
    requested_warmup=warmup
    if type(event_time_order) is not bool or type(require_explicit_forecast) is not bool:
        raise ValueError("invalid replay flags")
    if event_time_order:
        matches,warmup,groups,cutoffs=event_time_batches(matches,lambda m:m.kickoff_utc,warmup)
        cutoff_mode="EXPLICIT_RECORDED_FORECAST"
        cutoff_for=lambda row:cutoffs[row.fixture_id]
    else:
        matches,warmup,groups=ordered_batches(matches,lambda m:m.kickoff_utc,warmup)
        cutoffs,cutoff_mode=prediction_cutoffs(matches,lambda m:m.kickoff_utc,require_explicit=require_explicit_forecast)
        warmup=whole_forecast_warmup(matches,lambda m:m.kickoff_utc,cutoffs,warmup)
        cutoff_for=lambda row:cutoffs[utc(row.kickoff_utc)]
    state=State()
    clock=ResultClock()
    def apply(match):
        nonlocal state
        state=update(state,match.home_goals,match.away_goals)
    baseline=probabilities(score_matrix(1.4,1.1))
    losses={"baseline_brier":[],"baseline_log_loss":[],
            "challenger_brier":[],"challenger_log_loss":[]}
    for index,match in enumerate(matches):
        clock.drain_before(cutoff_for(match),apply)
        challenger=forecast(state)["probabilities"]
        outcome="home" if match.home_goals>match.away_goals else (
            "away" if match.home_goals<match.away_goals else "draw")
        if index >= warmup:
            for label,p in (("baseline",baseline),("challenger",challenger)):
                losses[label+"_brier"].append(multiclass_brier(p,outcome))
                losses[label+"_log_loss"].append(log_loss(p,outcome))
        clock.schedule(match.result_available_utc,match)
    return {"status":"RESEARCH_ONLY","production_recommendations":"DISABLED",
            "n_test":len(matches)-warmup,
            "requested_warmup":requested_warmup,"effective_warmup":warmup,"kickoff_groups":groups,
            "mean_metrics":{key:sum(vals)/len(vals) for key,vals in losses.items()},
            "verified_chronology":True,"team_specific_model":False,
            "result_availability_enforced":True,"availability_source_authenticated":False,
            "forecast_cutoff_mode":cutoff_mode,"forecast_clock_authenticated":False,
            "evaluation_order":"FORECAST_UTC" if event_time_order else "KICKOFF_UTC",
            "results_applied_before_last_forecast":clock.applied,
            "results_applied_before_last_kickoff":None if event_time_order else clock.applied,
            "qualified_for_production":False}
