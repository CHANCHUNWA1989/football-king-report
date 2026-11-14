"""Offline expanding walk-forward refits for explicitly supplied trusted history.

MatchHistory local timestamps and retrospective scores are NOT a valid input to
this runner. Caller must provide independently sourced UTC kickoff and result
availability instants; metadata alone does not establish their authenticity.
"""
from ops.penaltyblog_walkforward_refit import refit_walkforward


def refit_verified_history(history, targets, *, model="poisson", model_factory=None):
    if not isinstance(history, dict) or history.get("schema") != "football-king-private-utc-history-v1" or history.get("production_recommendations") != "DISABLED":
        raise ValueError("INVALID_HISTORY_ENVELOPE")
    if history.get("source_attestation_verified") is not True or history.get("result_availability_attested") is not True:
        raise ValueError("INDEPENDENT_SOURCE_AND_RESULT_ATTESTATION_REQUIRED")
    # No self-declared flag can establish an independent source. This handoff
    # deliberately fails closed until a trusted attestation verifier is wired.
    raise ValueError("TRUSTED_HISTORY_ATTESTATION_VERIFIER_NOT_IMPLEMENTED")


def refit_unverified_research(history_rows, targets, *, model="poisson", model_factory=None):
    """Research-only upstream refit, caller must supply full UTC row contract.

    Does not accept the soccerdata MatchHistory adapter's local-time records.
    """
    if not isinstance(history_rows, list) or not isinstance(targets, list):
        raise ValueError("INVALID_REFIT_INPUT")
    if any(not isinstance(r, dict) or set(r) != {
            "source_namespace", "event_id", "league_id", "home_team_id",
            "away_team_id", "kickoff_utc", "result_recorded_utc",
            "home_goals", "away_goals"} for r in history_rows):
        raise ValueError("EXPLICIT_UTC_HISTORY_REQUIRED")
    result = refit_walkforward({
        "schema": "football-king-penaltyblog-walkforward-v1",
        "production_recommendations": "DISABLED", "model": model,
        "historical_matches": history_rows, "targets": targets, "min_training": 30
    }, model_factory=model_factory)
    if result.get("production_recommendations") != "DISABLED" or result.get("independent_provenance_verified") is not False or result.get("positive_ev_verified") is not False:
        raise ValueError("UNSAFE_UPSTREAM_REFIT_RESULT")
    return result
