"""Observe one local callback execution, never certify a real in-play model.

Caller explicitly supplies a trusted local Python callable. This module is
NOT an importer/installer of the unmerged PR #433 model and does not prove
its implementation, code provenance, data source, timestamp, or OOS validity.
Output is always HOLD or RESEARCH_ONLY; formal recommendations disabled.
"""
import copy
import hashlib
import json
import math
from datetime import datetime, timezone

from inplay_remaining_goal_baseline import evaluate as baseline_evaluate, _utc
from inplay_same_snapshot_comparison import compare as compare_claims

SCHEMA = "football-king-inplay-local-execution-observation-v1"
SNAPSHOT_FIELDS = {
    "fixture_id", "kickoff_utc", "decision_utc", "minute_elapsed",
    "score_home", "score_away", "red_home", "red_away",
    "prematch", "event_consensus",
}
PRE_FIELDS = {
    "fixture_id", "model_id", "forecast_utc", "inputs_available_utc",
    "expected_home_goals", "expected_away_goals", "input_sha256",
    "production_recommendations", "calibrated",
}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _hash(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _base(reason="INVALID_INPUT", count=0):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "production_recommendations": "DISABLED",
        "local_callback_invocation_count": count,
        "callback_return_observed_in_process": False,
        "candidate_implementation_authenticated": False,
        "genuine_pr433_execution_proven": False,
        "externally_witnessed": False,
        "input_and_source_authenticated": False,
        "formal_model_comparison_allowed": False,
        "certified_paired_samples": 0,
        "model_scoring_eligible": False,
        "probabilities_calibrated": False,
        "positive_ev_verified": False,
        "recommendation": None, "stakes": None, "roi": None,
        "local_call_started_utc": None,
        "local_call_finished_utc": None,
        "input_sha256_unattested": None,
        "output_sha256_unattested": None,
        "comparison": None,
    }


def _preflight(case, snapshot):
    """Refuse an unrelated fixture/clock before calling any candidate."""
    if type(snapshot) is not dict or set(snapshot) != SNAPSHOT_FIELDS:
        raise ValueError("INVALID_CHALLENGER_SNAPSHOT_SCHEMA")
    fixture, state, pre = case["fixture"], case["state"], case["prematch"]
    if (snapshot["fixture_id"] != fixture["fixture_id"]
            or _utc(snapshot["kickoff_utc"]) != _utc(fixture["kickoff_utc"])):
        raise ValueError("FIXTURE_OR_KICKOFF_MISMATCH")
    if (type(snapshot["minute_elapsed"]) is not int
            or snapshot["minute_elapsed"] != state["elapsed_regulation_minutes"]
            or _utc(snapshot["decision_utc"]) != _utc(state["as_of_utc"])
            or any(type(snapshot[k]) is not int for k in
                   ("score_home", "score_away", "red_home", "red_away"))
            or (snapshot["score_home"], snapshot["score_away"],
                snapshot["red_home"], snapshot["red_away"]) != (
                state["home_goals"], state["away_goals"],
                state["home_red_cards"], state["away_red_cards"])):
        raise ValueError("MATCH_STATE_OR_DECISION_MISMATCH")
    p = snapshot["prematch"]
    if type(p) is not dict or set(p) != PRE_FIELDS:
        raise ValueError("INVALID_CHALLENGER_PREMATCH_SCHEMA")
    rates = (p.get("expected_home_goals"), p.get("expected_away_goals"))
    if (p["fixture_id"] != fixture["fixture_id"]
            or type(p["model_id"]) is not str or not p["model_id"].strip()
            or _utc(p["forecast_utc"]) != _utc(pre["generated_utc"])
            or _utc(p["inputs_available_utc"]) > _utc(p["forecast_utc"])
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in rates)
            or rates != (pre["home_goals_per_90"], pre["away_goals_per_90"])
            or p.get("calibrated") is not False
            or p.get("production_recommendations") != "DISABLED"):
        raise ValueError("PREMATCH_INPUT_NOT_SAME_SNAPSHOT")
    # Existing comparison performs the fuller post-call proof/output audit.


def observe_local(case, challenger_snapshot, candidate_callable):
    """Run *one* provided callable in-process, then inspect its returned claim.

    The caller controls the callable; running it locally is an observation,
    not an attestation of PR #433 code, trusted data or a prospective forecast.
    Do not pass arbitrary untrusted Python code as the callback.
    """
    baseline = baseline_evaluate(case)
    if baseline["status"] != "RESEARCH_ONLY":
        return _base("BASELINE_HOLD:" + baseline["reason"])
    if not callable(candidate_callable):
        return _base("CALLABLE_REQUIRED_NO_REPLAYED_OUTPUT")
    try:
        _preflight(case, challenger_snapshot)
        original_hash = _hash({"case": case, "snapshot": challenger_snapshot})
        argument = copy.deepcopy(challenger_snapshot)
        arg_hash = _hash(argument)
    except (KeyError, ValueError, TypeError, OverflowError, AttributeError):
        return _base("INVALID_OR_MISMATCHED_INPUT_SNAPSHOT")

    start = datetime.now(timezone.utc)
    # Intentionally do not retry after a callback error; no leakage of its
    # exception text, which might include provider secrets.
    try:
        returned = candidate_callable(argument)
    except Exception:
        return _base("CALLBACK_FAILED", count=1)
    end = datetime.now(timezone.utc)
    try:
        if (_hash(argument) != arg_hash or
                _hash({"case": case, "snapshot": challenger_snapshot}) != original_hash):
            return _base("CALLBACK_MUTATED_INPUT", count=1)
        paired = compare_claims(case, challenger_snapshot, returned)
        if paired["status"] != "RESEARCH_ONLY":
            return _base("CLAIMED_OUTPUT_FAILED_SAME_SNAPSHOT_AUDIT", count=1)
        output_hash = _hash(returned)
    except (ValueError, TypeError, OverflowError, AttributeError, KeyError):
        return _base("INVALID_CALLBACK_OUTPUT", count=1)
    return {**_base(), "status": "RESEARCH_ONLY",
            "reason": "LOCAL_CALLBACK_RETURN_OBSERVED_NO_INDEPENDENT_ATTESTATION",
            "local_callback_invocation_count": 1,
            "callback_return_observed_in_process": True,
            "local_call_started_utc": start.isoformat(),
            "local_call_finished_utc": end.isoformat(),
            "input_sha256_unattested": original_hash,
            "output_sha256_unattested": output_hash,
            "fixture_id": case["fixture"]["fixture_id"],
            "claimed_decision_utc": _utc(case["state"]["as_of_utc"]).isoformat(),
            "comparison": paired["comparison"]}
