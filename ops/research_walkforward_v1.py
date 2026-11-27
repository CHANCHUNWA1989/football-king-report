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

@dataclass(frozen=True)
class Match:
    kickoff_utc: datetime
    home_goals: int
    away_goals: int
    source_verified: bool = False

def _validate(matches: Sequence[Match]) -> None:
    previous = None
    for match in matches:
        if match.kickoff_utc.tzinfo is None or match.kickoff_utc.utcoffset() is None:
            raise ValueError("timezone-aware kickoff required")
        if not match.source_verified:
            raise ValueError("unverified history prohibited")
        if previous is not None and match.kickoff_utc <= previous:
            raise ValueError("history must be strictly chronological")
        previous = match.kickoff_utc
        if any(isinstance(v,bool) or not isinstance(v,int) or not 0<=v<=20
               for v in (match.home_goals,match.away_goals)):
            raise ValueError("invalid goals")

def walk_forward(matches: Sequence[Match], *, warmup: int=30) -> dict:
    """Prequential evaluation; forecast BEFORE observing each match result.

    Deliberately simplified aggregate state: NOT team-specific, NOT fitted GAS.
    This framework is an integration test, not evidence of forecasting uplift.
    """
    _validate(matches)
    if not isinstance(warmup,int) or warmup < 1 or len(matches) <= warmup:
        raise ValueError("insufficient chronological samples")
    state=State()
    baseline=probabilities(score_matrix(1.4,1.1))
    losses={"baseline_brier":[],"baseline_log_loss":[],
            "challenger_brier":[],"challenger_log_loss":[]}
    for index,match in enumerate(matches):
        challenger=forecast(state)["probabilities"]
        outcome="home" if match.home_goals>match.away_goals else (
            "away" if match.home_goals<match.away_goals else "draw")
        if index >= warmup:
            for label,p in (("baseline",baseline),("challenger",challenger)):
                losses[label+"_brier"].append(multiclass_brier(p,outcome))
                losses[label+"_log_loss"].append(log_loss(p,outcome))
        state=update(state,match.home_goals,match.away_goals)
    return {"status":"RESEARCH_ONLY","production_recommendations":"DISABLED",
            "n_test":len(matches)-warmup,
            "mean_metrics":{key:sum(vals)/len(vals) for key,vals in losses.items()},
            "verified_chronology":True,"team_specific_model":False,
            "qualified_for_production":False}
