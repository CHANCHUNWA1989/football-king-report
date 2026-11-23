"""Research-only projection of HKJC three-way handicap from an in-play Poisson baseline.

HKJC handicap HOME(+n) / DRAW(+n) / AWAY(-n) is three-way settlement:
a one-goal away victory with home +1 is a handicap DRAW, not an Asian push.
This is uncalibrated synthetic scenario math, not live/verified prediction, EV,
or advice to place a wager. Never use this output for production promotion.
"""
import math

from inplay_remaining_goal_baseline import evaluate as baseline_evaluate, _poisson

SCHEMA = "football-king-inplay-hkjc-threeway-research-v1"


def _project(home_score, away_score, remaining_home, remaining_away, home_handicap):
    """Return unrounded three-way mass for a discrete full-time score grid."""
    if (type(home_score) is not int or type(away_score) is not int
            or not 0 <= home_score <= 20 or not 0 <= away_score <= 20
            or type(home_handicap) is not int or not -3 <= home_handicap <= 3
            or any(type(v) not in (int, float) or not math.isfinite(v)
                   or not 0 <= v <= 10 for v in (remaining_home, remaining_away))):
        raise ValueError("INVALID_SCENARIO_PARAMETERS")
    probs = [0.0, 0.0, 0.0]
    for i, home_mass in enumerate(_poisson(remaining_home)):
        for j, away_mass in enumerate(_poisson(remaining_away)):
            diff = home_score + i + home_handicap - away_score - j
            probs[0 if diff > 0 else 1 if diff == 0 else 2] += home_mass * away_mass
    # Truncation should be negligible under the baseline bounded means.
    if not abs(sum(probs) - 1) < 1e-9:
        raise ValueError("POISSON_TAIL_NOT_COVERED")
    return probs


def evaluate(case, home_handicap=1):
    """Read the existing baseline's identical time/score assumptions; never certify.

    No live odds are read or inferred. A separately supplied market price, even
    one from an apparently legitimate screenshot, is forbidden here.
    """
    hold = {
        "schema": SCHEMA, "status": "HOLD", "reason": "INVALID_INPUT",
        "decision": "HOLD", "production_recommendations": "DISABLED",
        "model_scoring_eligible": False, "probabilities_calibrated": False,
        "event_source_authenticated": False, "point_in_time_externally_attested": False,
        "live_odds_verified": False, "positive_ev_verified": False,
        "betting_eligible": False, "recommendation": None,
        "roi": None, "stakes": None, "certified_forward_samples": 0,
        "scenarios": [],
    }
    if type(home_handicap) is not int or not -3 <= home_handicap <= 3:
        return {**hold, "reason": "INVALID_THREEWAY_HANDICAP"}
    base = baseline_evaluate(case)
    if base.get("status") != "RESEARCH_ONLY":
        return {**hold, "reason": "BASELINE_HOLD:" + str(base.get("reason", "UNKNOWN"))}
    if (base.get("schema") != "football-king-inplay-time-baseline-research-v1"
            or base.get("production_recommendations") != "DISABLED"
            or base.get("model_scoring_eligible") is not False
            or base.get("positive_ev_verified") is not False
            or len(base.get("scenarios", [])) != 3):
        return {**hold, "reason": "INCOMPATIBLE_BASELINE"}
    try:
        score_home, score_away = base["existing_score"]
        scenarios = []
        for row in base["scenarios"]:
            p = _project(score_home, score_away,
                         row["assumed_remaining_home_goals"],
                         row["assumed_remaining_away_goals"], home_handicap)
            scenarios.append({
                "goal_rate_multiplier": row["goal_rate_multiplier"],
                "assumed_remaining_home_goals": row["assumed_remaining_home_goals"],
                "assumed_remaining_away_goals": row["assumed_remaining_away_goals"],
                "home_handicap_win": round(p[0], 7),
                "handicap_draw": round(p[1], 7),
                "away_handicap_win": round(p[2], 7),
            })
        return {
            **hold, "status": "RESEARCH_ONLY",
            "reason": "HYPOTHETICAL_UNCALIBRATED_90MIN_THREEWAY_ONLY",
            "home_handicap": home_handicap,
            "handicap_contract": "HKJC_THREE_WAY_NOT_ASIAN_HANDICAP",
            "fixture_id": base["fixture_id"],
            "observed_utc": base["observed_utc"],
            "elapsed_regulation_minutes": base["elapsed_regulation_minutes"],
            "existing_score": list(base["existing_score"]),
            "excludes_stoppage_and_extra_time": True,
            "scenarios": scenarios,
        }
    except (TypeError, ValueError, KeyError, OverflowError):
        return {**hold, "reason": "INVALID_BASELINE_SCENARIO"}
