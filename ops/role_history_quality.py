"""Prospective football role-sample coverage guard; never a calibrated forecast.

A team's total history can hide a nearly empty home/away role sample.
Record the exact counts used by the frozen Poisson/shrinkage calculation so
downstream research shortlists can abstain without editing old predictions.
No historical outcome, odds, bookmaker price, or EV input is accepted.
"""
SCHEMA = "football-king-role-history-coverage-v1"
MIN_ROLE_GAMES = 3


def _count(value):
    return type(value) is int and 0 <= value <= 2000


def build(home_total_games, away_total_games, home_role_games, away_role_games):
    for value in (home_total_games, away_total_games, home_role_games, away_role_games):
        if not _count(value):
            raise ValueError("INVALID_ROLE_HISTORY_COUNT")
    if (home_total_games < 3 or away_total_games < 3
            or home_role_games > home_total_games
            or away_role_games > away_total_games):
        raise ValueError("CONTRADICTORY_ROLE_HISTORY_COUNT")
    enough = min(home_role_games, away_role_games) >= MIN_ROLE_GAMES
    return {
        "schema": SCHEMA,
        "home_team_total_games": home_total_games,
        "away_team_total_games": away_total_games,
        "home_team_home_games": home_role_games,
        "away_team_away_games": away_role_games,
        "minimum_per_role_games": MIN_ROLE_GAMES,
        "role_sample_sufficient_for_research": enough,
        "status": "ROLE_COVERAGE_RESEARCH_ONLY" if enough
                  else "THIN_ROLE_HISTORY_REVIEW_ONLY",
        "role_counts_source_authenticated": False,
        "model_calibration_verified": False,
        "eligible_for_betting": False,
        "production_recommendations": "DISABLED",
    }


def verify(value):
    """Reject impossible/forged statuses; do not trust caller eligibility flags."""
    if type(value) is not dict:
        raise ValueError("INVALID_ROLE_HISTORY_METADATA")
    try:
        expected = build(
            value["home_team_total_games"], value["away_team_total_games"],
            value["home_team_home_games"], value["away_team_away_games"]
        )
    except (KeyError, ValueError, TypeError):
        raise ValueError("INVALID_ROLE_HISTORY_METADATA") from None
    if value != expected:
        raise ValueError("INVALID_ROLE_HISTORY_METADATA")
    return expected
