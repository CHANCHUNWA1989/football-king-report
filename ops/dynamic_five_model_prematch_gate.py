"""Fifth model research-only attacher for SAME source/history/cutoff.

Takes *already complete*, never independently certified, A/Poisson/DC/
Bivariate in-process pre-match capture. Fits score-driven dynamic Poisson
only against exactly the same pre-cutoff history and records its own local
time window. Reject any partial, past, or inconsistent observation.
"""
from datetime import datetime, timedelta, timezone
import math

from .bivariate_four_model_prematch_gate import _clock, _probabilities
from .dynamic_score_driven_poisson import (
    SCHEMA as DYNAMIC_SCHEMA, MODEL_ID, predict_offline,
)
from .penaltyblog_research_bridge import _timestamp

SCHEMA = "football-king-five-model-prematch-observation-v1"
BUFFER = timedelta(minutes=10)


def _hold(reason, **extra):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "production_recommendations": "DISABLED", "model_promoted": False,
        "positive_ev_verified": False, "certified_prospective_samples": 0,
        "publisher_authenticity_verified": False,
        "result_publication_time_witnessed": False,
        "independently_timestamped": False,
        "market_odds_or_ev_verified": False,
        **extra,
    }


def attach(payload, four_model, *, clock):
    """Allow a fifth shadow diagnostic only BEFORE the same cutoff.

    Never consume a retrospective score or unverified four-model envelope as
    if it were signed prospective proof. Even a success remains HOLD.
    """
    if type(payload) is not dict or type(four_model) is not dict or not callable(clock):
        return _hold("INVALID_FIVE_MODEL_INPUT")
    try:
        original = payload["original_a"]
        history = payload["historical_matches"]
        cutoff = _timestamp(payload["decision_cutoff_utc"])
        kickoff = _timestamp(original["kickoff_utc"])
        if (payload.get("production_recommendations") != "DISABLED"
                or four_model.get("reason") != "LOCAL_FOUR_MODEL_PREMATCH_CAPTURE_UNATTESTED"
                or four_model.get("status") != "HOLD"
                or four_model.get("production_recommendations") != "DISABLED"
                or four_model.get("positive_ev_verified") is not False
                or four_model.get("model_promoted") is not False
                or four_model.get("certified_prospective_samples") != 0
                or four_model.get("source_native_a_history_set_matches_challengers") is not True
                or four_model.get("training_match_count") != len(history)):
            return _hold("FOUR_MODEL_RESEARCH_GATE_UNTRUSTED")
        check = (
            four_model["fixture_id"] == original["event_id"]
            and four_model["source_namespace"] == original["source_namespace"]
            and four_model["league_id"] == original["league_id"]
            and _timestamp(four_model["kickoff_utc"]) == kickoff
            and _timestamp(four_model["decision_cutoff_utc"]) == cutoff
            and four_model["original_a_1x2"] == original["probabilities"]
            and all(_probabilities(four_model[name]) for name in (
                "original_a_1x2", "poisson_1x2", "dixon_coles_1x2",
                "bivariate_poisson_1x2"))
        )
        if not check:
            return _hold("FOUR_MODEL_FIXTURE_OR_PROBABILITY_MISMATCH")
        after_four = _timestamp(four_model["local_fourth_model_finished_utc"])
        started = _clock(clock)
        if not after_four <= started < cutoff < kickoff - BUFFER:
            return _hold("FIFTH_MODEL_NOT_PREMATCH_OR_AFTER_CUTOFF")
        request = {
            "schema": DYNAMIC_SCHEMA,
            "production_recommendations": "DISABLED",
            "as_of_utc": payload["decision_cutoff_utc"],
            "target_fixture": {
                k: original[k] for k in (
                    "source_namespace", "event_id", "league_id",
                    "home_team_id", "away_team_id", "kickoff_utc")
            },
            "historical_matches": history,
        }
        result = predict_offline(request)
        ended = _clock(clock)
        if not started <= ended <= cutoff or ended >= kickoff - BUFFER:
            return _hold("FIFTH_MODEL_CROSSED_PREMATCH_CUTOFF")
        if (result.get("status") != "HOLD"
                or result.get("reason") != "UNVERIFIED_DYNAMIC_POISSON_RESEARCH_ONLY"
                or result.get("model_id") != MODEL_ID
                or result.get("source_namespace") != original["source_namespace"]
                or result.get("league_id") != original["league_id"]
                or result.get("fixture_id") != original["event_id"]
                or _timestamp(result.get("kickoff_utc")) != kickoff
                or _timestamp(result.get("as_of_utc")) != cutoff
                or result.get("training_match_count") != len(history)
                or result.get("model_promoted") is not False
                or result.get("positive_ev_verified") is not False
                or not _probabilities(result.get("p_home_draw_away"))):
            return _hold("DYNAMIC_FIT_OR_TIME_OR_SOURCE_MISMATCH")
        return _hold(
            "LOCAL_FIVE_MODEL_PREMATCH_RESEARCH_UNATTESTED",
            fixture_id=original["event_id"],
            source_namespace=original["source_namespace"],
            league_id=original["league_id"],
            kickoff_utc=kickoff.isoformat(),
            decision_cutoff_utc=cutoff.isoformat(),
            local_fifth_model_started_utc=started.isoformat(),
            local_fifth_model_finished_utc=ended.isoformat(),
            original_a_1x2=four_model["original_a_1x2"],
            poisson_1x2=four_model["poisson_1x2"],
            dixon_coles_1x2=four_model["dixon_coles_1x2"],
            bivariate_poisson_1x2=four_model["bivariate_poisson_1x2"],
            dynamic_score_poisson_1x2=result["p_home_draw_away"],
            dynamic_expected_home_goals=result["expected_home_goals"],
            dynamic_expected_away_goals=result["expected_away_goals"],
            dynamic_over_2_75_settlement=result["over_total_goals_settlement"]["2.75"],
            dynamic_home_ah_minus_0_25_settlement=result[
                "home_asian_handicap_settlement"]["-0.25"],
            history_source_match_count=len(history),
            dynamic_model_research_shadow_only=True,
            source_publisher_independent_witness=False,
            all_five_eligible_for_betting=False,
            note=("All results use one local research history and cutoff; "
                  "not independently attested, no authentic bookmaker odds, "
                  "no calibrated EV or return on investment."),
        )
    except (KeyError, ValueError, TypeError, OverflowError, AttributeError):
        return _hold("INVALID_FIVE_MODEL_RESEARCH_PAYLOAD")
