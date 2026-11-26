"""Deep handicap diagnostics; research-only, no quote or recommendation.

Independent Poisson scenario assumptions, not estimated tactical effects.
Reuse the existing Asian handicap grader and validated Poisson support.
"""
import math
from asian_handicap_research import TYPES, grade, quarter_units, _poisson
from deep_handicap_joint_score import score_distribution

SCHEMA = "football-king-deep-handicap-diagnostics-v1"
FACTORS = (0.85, 1.0, 1.15)
PACE_FACTORS = (0.65, 0.85, 1.0)


def _joint(home, away, side, line, pace=1.0):
    """Two independent half-periods; second-half favourite rate changes
    only if ahead by >=2 at half-time. This is a hypothetical stress test,
    not a fitted or live-state model. Half-rate generation uses full-rate
    validation upstream and recurrence with explicit normalized support.
    """
    margins = {}
    for (h, a), probability in score_distribution(home, away, side, pace).items():
        m = h-a if side == "HOME" else a-h
        margins[m] = margins.get(m, 0.0) + probability
    # Tail beyond grader's score boundary is negligible; grade by equivalent
    # bounded margin because the supported line is at most five goals.
    grades = dict.fromkeys(TYPES, 0.0)
    buckets = {"NOT_WIN": 0.0, "WIN_1": 0.0, "WIN_2": 0.0,
               "WIN_3": 0.0, "WIN_4_PLUS": 0.0}
    win_with_loss = 0.0
    for m, p in margins.items():
        bounded = max(-25, min(25, m))
        # Here scores are oriented to the favourite regardless of home/away.
        g = grade(max(0, bounded), max(0, -bounded), "HOME", line)
        grades[g] += p
        key = ("NOT_WIN" if m <= 0 else "WIN_4_PLUS" if m >= 4
               else "WIN_" + str(m))
        buckets[key] += p
        if m > 0 and g in ("HALF_LOSS", "FULL_LOSS"):
            win_with_loss += p
    if abs(math.fsum(grades.values()) - 1) > 1e-9:
        raise ValueError("INVALID_PROBABILITY_MASS")
    return {"grades": grades, "margin_buckets": buckets,
            "win_probability": 1-buckets["NOT_WIN"],
            "win_but_stake_loss_probability": win_with_loss}


def analyze(home, away, side, handicap):
    """Return diagnostics and a 27-scenario uncertainty envelope.
    Invalid inputs raise; invalid stress bounds explicitly return HOLD.
    No odds, stake sizes, ROI or actual market qualification are emitted.
    """
    units = quarter_units(handicap)
    if units > -6 or side not in ("HOME", "AWAY"):
        raise ValueError("REQUIRES_FAVOURITE_DEEP_LINE")
    _poisson(home)
    _poisson(away)
    out = {"schema": SCHEMA, "status": "HOLD", "research_only": True,
           "production_recommendations": "DISABLED",
           "qualifies_for_betting": False,
           "positive_expected_value_verified": False,
           "calibrated": False, "actual_market_line_verified": False,
           "hypothetical_line": units/4, "side": side,
           "baseline": _joint(home, away, side, units/4)}
    scenarios = []
    for h in FACTORS:
        for a in FACTORS:
            for pace in PACE_FACTORS:
                try:
                    v = _joint(home*h, away*a, side, units/4, pace)
                except ValueError:
                    out.update(stress_status="INCOMPLETE_RATE_DOMAIN",
                               stress_scenario_count=len(scenarios))
                    return out
                scenarios.append(v)
    def interval(values):
        return {"min": min(values), "max": max(values)}
    out.update(stress_status="SYNTHETIC_ONLY", stress_scenario_count=len(scenarios),
               full_win_envelope=interval([s["grades"]["FULL_WIN"] for s in scenarios]),
               win_but_stake_loss_envelope=interval(
                   [s["win_but_stake_loss_probability"] for s in scenarios]),
               assumptions={"rate_multipliers": FACTORS, "second_half_pace": PACE_FACTORS,
                            "trigger": "FAVOURITE_AHEAD_BY_TWO_AT_HALF_TIME",
                            "not_fitted": True})
    return out
