"""Zero-network research audit for the frozen Poisson 1X2 12-goal cutoff.

The historical baseline sums scorelines 0..11 for each team, then normalizes
the retained probability mass. This changes its output for high goal rates.
This module reports numerical error only: it must not modify archived
forecasts, set weights, claim calibration, or enable betting.
"""
import math

LEGACY_GOALS = 12
REFERENCE_GOALS = 64
MAX_SUPPORTED_RATE = 5.5
DEFAULT_ALERT_DELTA_PP = 0.1

def _rate(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("INVALID_POISSON_RATE")
    rate = float(value)
    if not 0.1 <= rate <= MAX_SUPPORTED_RATE:
        raise ValueError("RATE_OUTSIDE_FROZEN_MODEL_RANGE")
    return rate

def _weights(rate, count):
    values = [math.exp(-rate)]
    for goals in range(1, count):
        values.append(values[-1] * rate / goals)
    return values

def _score_matrix(home_rate, away_rate, count):
    home = _weights(home_rate, count)
    away = _weights(away_rate, count)
    vector = [0.0, 0.0, 0.0]
    for hg, hp in enumerate(home):
        for ag, ap in enumerate(away):
            idx = 0 if hg > ag else 1 if hg == ag else 2
            vector[idx] += hp * ap
    mass = sum(vector)
    if not 0 < mass <= 1.0 + 1e-12:
        raise ValueError("INVALID_POISSON_MASS")
    return [x / mass for x in vector], mass

def audit(home_rate, away_rate, *, alert_delta_pp=DEFAULT_ALERT_DELTA_PP):
    """Compare *unchanged* legacy score PMF with a 64-goal reference.

    The reported reference is numerical only, not an independently validated
    football forecast. All output remains research-only/HOLD. The optional
    threshold is in percentage points, not probability units.
    """
    home = _rate(home_rate)
    away = _rate(away_rate)
    if (type(alert_delta_pp) not in (int, float)
            or not math.isfinite(alert_delta_pp)
            or not 0 < alert_delta_pp <= 5):
        raise ValueError("INVALID_AUDIT_THRESHOLD")
    old, old_mass = _score_matrix(home, away, LEGACY_GOALS)
    new, new_mass = _score_matrix(home, away, REFERENCE_GOALS)
    if abs(1.0 - new_mass) > 1e-12:
        raise ValueError("REFERENCE_TAIL_NOT_CONVERGED")
    deviation = max(abs(a - b) for a, b in zip(old, new)) * 100
    alert = deviation > alert_delta_pp
    return {
        "schema": "football-king-poisson-tail-numerical-audit-v1",
        "status": "HOLD" if alert else "RESEARCH_ONLY",
        "reason": "LEGACY_TRUNCATION_EXCEEDS_TOLERANCE"
                  if alert else "NO_MATERIAL_NUMERICAL_DELTA_AT_THRESHOLD",
        "home_expected_goals": home,
        "away_expected_goals": away,
        "legacy_max_goals_per_team": LEGACY_GOALS - 1,
        "reference_max_goals_per_team": REFERENCE_GOALS - 1,
        "legacy_retained_mass": round(old_mass, 12),
        "legacy_excluded_mass_percent": round(max(0.0, 1-old_mass) * 100, 6),
        "reference_excluded_mass_upper_bound": 1e-12,
        "legacy_1x2": [round(v, 9) for v in old],
        "reference_1x2": [round(v, 9) for v in new],
        "max_probability_delta_percentage_points": round(deviation, 6),
        "alert_threshold_percentage_points": float(alert_delta_pp),
        "numerical_truncation_risk_flag": alert,
        "original_frozen_forecast_modified": False,
        "model_accuracy_improved_proven": False,
        "independent_calibration_authenticated": False,
        "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
    }
