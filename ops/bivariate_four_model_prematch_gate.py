"""Fourth challenger on an existing same-response A/Poisson/DC capture.

This is an in-process, PRE-KICKOFF, read-only research add-on, not a trusted
source/timestamp witness. No retroactive results, historical refits after
kickoff, automated wagers, source harvesting or release privileges.
"""
from datetime import datetime, timedelta, timezone
import math

from .penaltyblog_a_dual_prematch_capture import _timestamp
from .penaltyblog_bivariate_goals_challenger import (
    SCHEMA as BIVARIATE_SCHEMA, compare as compare_bivariate,
)

SCHEMA = "football-king-four-model-prematch-observation-v1"
BUFFER = timedelta(minutes=10)


def _hold(reason, **details):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "production_recommendations": "DISABLED", "positive_ev_verified": False,
        "model_promoted": False, "certified_prospective_samples": 0,
        "source_authenticity_verified": False,
        "independent_timestamp_attestation": False,
        "bookmaker_quotes_verified": False,
        **details,
    }


def _clock(clock):
    moment = clock()
    if (type(moment) is not datetime or moment.tzinfo is None
            or moment.utcoffset() is None):
        raise ValueError("INVALID_LOCAL_CLOCK")
    return moment.astimezone(timezone.utc)


def _probabilities(value):
    return (type(value) is list and len(value) == 3
            and all(type(x) in (float, int) and
                    math.isfinite(x) and 0 <= x <= 1 for x in value)
            and abs(sum(value) - 1.0) <= 1e-6)


def attach(payload, three_model, *, same_a_training_rows, clock, model_factory=None):
    """Accept no four-model observation unless *all* observations are pre-cutoff.

    The A model remains the original prediction produced by its own algorithm.
    A historical-coverage check must be supplied from the SAME one-GET source:
    it is not inferred from this adapter's native IDs or display names.
    """
    if (type(same_a_training_rows) is not bool
            or same_a_training_rows is not True
            or type(payload) is not dict
            or type(three_model) is not dict):
        return _hold("A_AND_CHALLENGERS_HISTORY_NOT_IDENTICAL")
    try:
        if (three_model.get("status") != "HOLD"
                or three_model.get("reason") != "LOCAL_A_POISSON_DC_CAPTURE_NOT_EXTERNALLY_ATTESTED"
                or three_model.get("production_recommendations") != "DISABLED"
                or three_model.get("positive_ev_verified") is not False
                or three_model.get("certified_prospective_samples") != 0
                or payload.get("production_recommendations") != "DISABLED"):
            return _hold("UNTRUSTED_THREE_MODEL_CAPTURE")
        body = three_model["unverified_triple_capture"]
        original = payload["original_a"]
        history = payload["historical_matches"]
        cutoff = _timestamp(payload["decision_cutoff_utc"])
        kickoff = _timestamp(original["kickoff_utc"])
        if not (body["event_id"] == original["event_id"]
                and body["source_namespace"] == original["source_namespace"]
                and body["league_id"] == original["league_id"]
                and body["home_team_id"] == original["home_team_id"]
                and body["away_team_id"] == original["away_team_id"]
                and _timestamp(body["decision_cutoff_utc"]) == cutoff
                and _timestamp(body["kickoff_utc"]) == kickoff
                and body["original_a_probabilities"] == original["probabilities"]
                and _probabilities(original["probabilities"])):
            return _hold("A_TRIPLE_FIXTURE_OR_TIME_MISMATCH")
        observations = body["challenger_observations"]
        if (type(observations) is not list or len(observations) != 2
                or [o.get("model") for o in observations] != ["poisson", "dixon_coles"]
                or any(not _probabilities(o.get("probabilities")) for o in observations)
                or any(o.get("training_match_count") != len(history)
                       for o in observations)):
            return _hold("INCOMPLETE_THREE_MODEL_CAPTURE")
        last_three = _timestamp(body["last_local_capture_observed_utc"])
        start = _clock(clock)
        if not last_three <= start < cutoff < kickoff - BUFFER:
            return _hold("FOURTH_MODEL_NOT_PREMATCH_OR_AFTER_CUTOFF")
        request = {
            "schema": BIVARIATE_SCHEMA,
            "production_recommendations": "DISABLED",
            "model": "bivariate_poisson",
            "as_of_utc": payload["decision_cutoff_utc"],
            "target_fixture": {
                key: original[key] for key in (
                    "source_namespace", "event_id", "league_id",
                    "home_team_id", "away_team_id", "kickoff_utc")
            },
            "historical_matches": history,
        }
        model = compare_bivariate(request, model_factory=model_factory)
        end = _clock(clock)
        if not start <= end <= cutoff or end >= kickoff - BUFFER:
            return _hold("FOURTH_MODEL_EXECUTION_CROSSED_CUTOFF")
        if (model.get("status") != "HOLD"
                or model.get("reason") != "UNVERIFIED_BIVARIATE_RESEARCH_ONLY"
                or model.get("fixture_id") != body["event_id"]
                or model.get("league_id") != body["league_id"]
                or model.get("source_namespace") != body["source_namespace"]
                or _timestamp(model.get("as_of_utc")) != cutoff
                or model.get("training_match_count") != len(history)
                or model.get("positive_ev_verified") is not False
                or model.get("model_promoted") is not False):
            return _hold("FOURTH_MODEL_FIT_OR_SOURCE_MISMATCH")
        fourth = model["models"]["unweighted"]
        weighted = model["models"]["time_weighted"]
        return _hold(
            "LOCAL_FOUR_MODEL_PREMATCH_CAPTURE_UNATTESTED",
            fixture_id=body["event_id"], kickoff_utc=kickoff.isoformat(),
            source_namespace=body["source_namespace"], league_id=body["league_id"],
            decision_cutoff_utc=cutoff.isoformat(),
            local_fourth_model_started_utc=start.isoformat(),
            local_fourth_model_finished_utc=end.isoformat(),
            original_a_1x2=original["probabilities"],
            poisson_1x2=observations[0]["probabilities"],
            dixon_coles_1x2=observations[1]["probabilities"],
            bivariate_poisson_1x2=fourth["probabilities_1x2_home_draw_away"],
            bivariate_poisson_time_decay_1x2=weighted["probabilities_1x2_home_draw_away"],
            bivariate_over_2_75_settlement=fourth["over_total_goals_settlement"]["2.75"],
            bivariate_home_ah_minus_0_25_settlement=fourth[
                "home_asian_handicap_settlement"]["-0.25"],
            training_match_count=len(history),
            source_native_a_history_set_matches_challengers=True,
            provider_results_first_publication_time_verified=False,
            all_four_predictions_eligible_for_production=False,
            note=("Local clock and exact one-response training inputs, not "
                  "independently signed source or forecast. No authentic odds/EV."),
        )
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
        return _hold("INVALID_FOUR_MODEL_PREMATCH_INPUT_OR_TIME")
