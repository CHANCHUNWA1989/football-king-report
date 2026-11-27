"""Offline GAS-style score-driven team attack/defence prototype.

Research-only. No fitted parameters, live sources or production integration.
The innovation is a bounded score-driven update, not a validated forecast.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from ops.research_multimodel_v1 import score_matrix, probabilities

@dataclass(frozen=True)
class State:
    home_attack: float = 0.0
    home_defence: float = 0.0
    away_attack: float = 0.0
    away_defence: float = 0.0

def _finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError(name + " must be finite")
    return float(value)

def _clamp(value: float, bound: float=1.5) -> float:
    return max(-bound,min(bound,value))

def forecast(state: State, baseline_home: float=1.4, baseline_away: float=1.1) -> dict:
    for value in vars(state).values():
        _finite(value,"state")
    for rate in (baseline_home,baseline_away):
        if not 0 < _finite(rate,"baseline") <= 3:
            raise ValueError("baseline out of research range")
    # The score matrix has finite support. Bound forecast rates so extreme
    # synthetic stress states remain numerically representable.
    home=min(6.0,baseline_home*math.exp(_clamp(state.home_attack-state.away_defence)))
    away=min(6.0,baseline_away*math.exp(_clamp(state.away_attack-state.home_defence)))
    return {"lambda_home":home,"lambda_away":away,
            "probabilities":probabilities(score_matrix(home,away))}

def update(state: State, home_goals: int, away_goals: int,
           *, step: float=0.04, persistence: float=0.98) -> State:
    """One prequential score update; must only run AFTER the observed match."""
    if any(isinstance(v,bool) or not isinstance(v,int) or not 0<=v<=20
           for v in (home_goals,away_goals)):
        raise ValueError("invalid observed goals")
    if not 0 < _finite(step,"step") <= 0.2 or not 0<=_finite(persistence,"persistence")<=1:
        raise ValueError("invalid hyperparameters")
    pred=forecast(state)
    # Clip surprise to bound influence of extreme scores.
    eh=_clamp(home_goals-pred["lambda_home"],3.0)
    ea=_clamp(away_goals-pred["lambda_away"],3.0)
    return State(
        home_attack=_clamp(persistence*state.home_attack+step*eh),
        home_defence=_clamp(persistence*state.home_defence-step*ea),
        away_attack=_clamp(persistence*state.away_attack+step*ea),
        away_defence=_clamp(persistence*state.away_defence-step*eh))
