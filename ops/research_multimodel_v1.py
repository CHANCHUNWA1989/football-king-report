"""Research-only multi-model score matrix and calibration guards.

No bookmaker feed, model training, production integration or betting execution.
"""
from __future__ import annotations
import math
from typing import Mapping

MAX_GOALS = 15

def _check_rate(rate: float) -> float:
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate <= 0 or rate > 10:
        raise ValueError("expected goals must be finite in (0, 10]")
    return float(rate)

def poisson_pmf(rate: float, cap: int = MAX_GOALS) -> list[float]:
    rate = _check_rate(rate)
    if not isinstance(cap, int) or cap < 1 or cap > 100:
        raise ValueError("invalid cap")
    values = [math.exp(-rate)]
    for k in range(1, cap + 1):
        values.append(values[-1] * rate / k)
    return values

def score_matrix(home_xg: float, away_xg: float, cap: int = MAX_GOALS) -> list[list[float]]:
    # Expand finite support rather than silently renormalizing large tails.
    # At the maximum permitted rate (10), 60 goals is safely sufficient.
    if not isinstance(cap, int) or isinstance(cap, bool) or not 1 <= cap <= 100:
        raise ValueError("invalid cap")
    while True:
        home, away = poisson_pmf(home_xg, cap), poisson_pmf(away_xg, cap)
        mass = sum(home) * sum(away)
        if mass >= 0.999999:
            break
        if cap >= 60:
            raise ValueError("score truncation exceeds tolerance")
        cap = min(60, cap + 5)
    return [[h * a / mass for a in away] for h in home]

def dixon_coles(home_xg: float, away_xg: float, rho: float = -0.1) -> list[list[float]]:
    """Low-score correction, research scenario rho only; not fitted."""
    h, a = _check_rate(home_xg), _check_rate(away_xg)
    if not math.isfinite(rho) or abs(rho) > 0.25:
        raise ValueError("rho outside research bounds")
    m = score_matrix(h, a)
    factors = {(0, 0): 1 - h*a*rho, (0, 1): 1 + h*rho,
               (1, 0): 1 + a*rho, (1, 1): 1-rho}
    for (i,j), factor in factors.items():
        if factor < 0:
            raise ValueError("invalid low-score factor")
        m[i][j] *= factor
    z = sum(map(sum,m))
    return [[v/z for v in row] for row in m]

def probabilities(matrix: list[list[float]]) -> dict[str,float]:
    if not matrix or any(len(row) != len(matrix) for row in matrix):
        raise ValueError("square score matrix required")
    if any(not math.isfinite(v) or v < 0 for row in matrix for v in row):
        raise ValueError("invalid probability")
    total = sum(map(sum,matrix))
    if abs(total-1) > 1e-8:
        raise ValueError("probability mass not normalized")
    return {"home":sum(v for i,row in enumerate(matrix) for j,v in enumerate(row) if i>j),
            "draw":sum(row[i] for i,row in enumerate(matrix)),
            "away":sum(v for i,row in enumerate(matrix) for j,v in enumerate(row) if i<j)}

def multiclass_brier(prediction: Mapping[str,float], outcome: str) -> float:
    if outcome not in ("home","draw","away"):
        raise ValueError("invalid outcome")
    vals=[prediction[k] for k in ("home","draw","away")]
    if any(not math.isfinite(x) or x<0 or x>1 for x in vals) or abs(sum(vals)-1)>1e-8:
        raise ValueError("invalid forecast")
    return sum((p-float(k==outcome))**2 for k,p in zip(("home","draw","away"),vals))

def log_loss(prediction: Mapping[str,float], outcome: str) -> float:
    multiclass_brier(prediction,outcome)
    return -math.log(max(prediction[outcome],1e-15))

def research_gate(*, independent_oos: bool=False, verified_sources: bool=False,
                  executable_quote: bool=False, calibrated: bool=False) -> dict[str,object]:
    """Never promotes research into production: deployment requires separate approval."""
    missing=[name for name,passed in (("independent_oos",independent_oos),
             ("verified_sources",verified_sources),("executable_quote",executable_quote),
             ("calibrated",calibrated)) if not passed]
    return {"status":"HOLD","production_recommendations":"DISABLED",
            "missing_evidence":missing,"research_only":True}
