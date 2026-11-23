"""Fail-closed in-play 1X2 comparison *readiness*, not performance scoring.

Stacks on the separate remaining-time research baseline PR. It accepts a
caller-supplied, unverified PR-433-shaped challenger snapshot and report;
neither the execution of that challenger nor the source event is authenticated.
Never count this as a prospective sample or compare it to a final result.
"""
import math

from inplay_remaining_goal_baseline import evaluate as baseline_evaluate, _utc

SCHEMA = "football-king-inplay-same-snapshot-comparison-v1"
CHALLENGER_SCHEMA = "football-king-vnext-inplay-comeback-challenger-v1"
CHALLENGER_MODEL = "inplay-fixed-score-state-v1-uncalibrated"
SIDES = ("HOME", "DRAW", "AWAY")


def _hold(reason):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "production_recommendations": "DISABLED",
        "model_scoring_eligible": False,
        "eligible_for_formal_comparison": False,
        "prediction_execution_authenticated": False,
        "event_and_prematch_inputs_authenticated": False,
        "prospective_capture_witnessed": False,
        "probabilities_calibrated": False,
        "positive_ev_verified": False,
        "certified_paired_samples": 0,
        "recommendation": None, "stakes": None, "roi": None,
        "comparison": None,
    }


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _same_time(left, right):
    return _utc(left) == _utc(right)


def _probabilities(value):
    _require(type(value) is dict and set(value) == set(SIDES),
             "INVALID_CHALLENGER_PROBABILITY_VECTOR")
    _require(all(type(value[k]) in (float, int)
                 and math.isfinite(value[k]) and 0 <= value[k] <= 1
                 for k in SIDES), "INVALID_CHALLENGER_PROBABILITY_VECTOR")
    _require(abs(math.fsum(value[k] for k in SIDES) - 1) <= 1e-7,
             "INVALID_CHALLENGER_PROBABILITY_MASS")
    return {k: float(value[k]) for k in SIDES}


def _digest(value):
    return (type(value) is str and len(value) == 64
            and all(k in "0123456789abcdef" for k in value))


def compare(case, challenger_snapshot, challenger_output):
    """Compare *claimed* outputs only when inputs have identical stated PIT.

    Same strings / timestamps cannot authenticate that a model actually ran.
    Consequently a successful result is not eligible for settlement, OOS
    accuracy, EV, ROI, CLV or real-world betting. Reject every extra field.
    """
    result = _hold("INVALID_INPUT")
    baseline = baseline_evaluate(case)
    if baseline["status"] != "RESEARCH_ONLY":
        return {**result, "reason": "BASELINE_HOLD:" + baseline["reason"]}
    try:
        _require(type(challenger_snapshot) is dict and set(challenger_snapshot) == {
            "fixture_id", "kickoff_utc", "decision_utc", "minute_elapsed",
            "score_home", "score_away", "red_home", "red_away",
            "prematch", "event_consensus"}, "INVALID_CHALLENGER_SNAPSHOT_SCHEMA")
        state = case["state"]
        fixture = case["fixture"]
        pre = case["prematch"]
        snap = challenger_snapshot
        _require(snap["fixture_id"] == fixture["fixture_id"]
                 and _same_time(snap["kickoff_utc"], fixture["kickoff_utc"]),
                 "FIXTURE_OR_KICKOFF_MISMATCH")
        _require(_same_time(snap["decision_utc"], state["as_of_utc"])
                 and type(snap["minute_elapsed"]) is int
                 and snap["minute_elapsed"] == state["elapsed_regulation_minutes"]
                 and all(type(snap[k]) is int for k in (
                     "score_home", "score_away", "red_home", "red_away"))
                 and snap["score_home"] == state["home_goals"]
                 and snap["score_away"] == state["away_goals"]
                 and snap["red_home"] == state["home_red_cards"]
                 and snap["red_away"] == state["away_red_cards"],
                 "MATCH_STATE_OR_DECISION_MISMATCH")
        p = snap["prematch"]
        _require(type(p) is dict and set(p) == {
            "fixture_id", "model_id", "forecast_utc", "inputs_available_utc",
            "expected_home_goals", "expected_away_goals", "input_sha256",
            "production_recommendations", "calibrated"},
            "INVALID_CHALLENGER_PREMATCH_SCHEMA")
        _require(p["fixture_id"] == fixture["fixture_id"]
                 and type(p["model_id"]) is str and bool(p["model_id"].strip())
                 and _same_time(p["forecast_utc"], pre["generated_utc"])
                 and _utc(p["inputs_available_utc"]) <= _utc(p["forecast_utc"])
                 and type(p["expected_home_goals"]) in (int, float)
                 and type(p["expected_away_goals"]) in (int, float)
                 and p["expected_home_goals"] == pre["home_goals_per_90"]
                 and p["expected_away_goals"] == pre["away_goals_per_90"]
                 and _digest(p["input_sha256"])
                 and p["production_recommendations"] == "DISABLED"
                 and p["calibrated"] is False, "PREMATCH_INPUT_NOT_SAME_SNAPSHOT")
        proof = snap["event_consensus"]
        _require(type(proof) is dict and not (set(proof) & {
            "result", "final_result", "final_score", "odds", "market_odds",
            "bookmaker_quote", "wager", "stake", "roi", "ev"}),
            "POSTMATCH_OR_MARKET_DATA_IN_EVENT_PROOF")
        _require(type(proof) is dict
                 and proof.get("status") == "RESEARCH_ONLY"
                 and proof.get("fixture_id") == fixture["fixture_id"]
                 and _same_time(proof.get("decision_utc"), state["as_of_utc"])
                 and all(type(proof.get(k)) is int for k in ("score_home", "score_away"))
                 and proof["score_home"] == state["home_goals"]
                 and proof["score_away"] == state["away_goals"]
                 and type(proof.get("active_red_cards")) is dict
                 and set(proof["active_red_cards"]) == {"HOME", "AWAY"}
                 and all(type(proof["active_red_cards"][k]) is int
                         and proof["active_red_cards"][k] == 0
                         for k in ("HOME", "AWAY"))
                 and proof.get("production_recommendations") == "DISABLED"
                 and proof.get("model_scoring_eligible") is False
                 and proof.get("source_authenticated") is False
                 and proof.get("source_independence_verified") is False
                 and _digest(proof.get("evidence_input_sha256")),
                 "UNTRUSTED_OR_MISMATCHED_EVENT_CONSENSUS")
        o = challenger_output
        allowed_report_fields = {
            "schema", "status", "model_id", "fixture_id", "decision_utc",
            "minute_elapsed", "current_score", "input_evidence_sha256_unattested",
            "prematch_input_sha256_unattested", "remaining_expected_home_goals",
            "remaining_expected_away_goals", "fulltime_probabilities", "trailing_team",
            "trailing_team_comeback_win_probability", "top_fulltime_scores",
            "fixed_coefficients_not_trained", "stoppage_time_not_modelled",
            "independent_clock_attestation", "source_authenticated", "model_calibrated",
            "model_scoring_eligible", "positive_ev_verified",
            "betting_recommendation_allowed", "production_recommendations"}
        _require(type(o) is dict and set(o) == allowed_report_fields,
                 "INVALID_CHALLENGER_OUTPUT_SCHEMA")
        _require(type(o) is dict and o.get("schema") == CHALLENGER_SCHEMA
                 and o.get("model_id") == CHALLENGER_MODEL
                 and o.get("status") == "RESEARCH_ONLY"
                 and o.get("fixture_id") == fixture["fixture_id"]
                 and _same_time(o.get("decision_utc"), state["as_of_utc"])
                 and type(o.get("minute_elapsed")) is int
                 and o["minute_elapsed"] == state["elapsed_regulation_minutes"]
                 and type(o.get("current_score")) is list
                 and len(o["current_score"]) == 2
                 and all(type(k) is int for k in o["current_score"])
                 and o["current_score"] == [state["home_goals"], state["away_goals"]]
                 and o.get("prematch_input_sha256_unattested") == p["input_sha256"]
                 and o.get("input_evidence_sha256_unattested") == proof["evidence_input_sha256"]
                 and o.get("fixed_coefficients_not_trained") is True
                 and o.get("stoppage_time_not_modelled") is True
                 and all(o.get(k) is False for k in (
                     "independent_clock_attestation", "source_authenticated",
                     "model_calibrated", "model_scoring_eligible", "positive_ev_verified",
                     "betting_recommendation_allowed"))
                 and o.get("production_recommendations") == "DISABLED",
                 "UNTRUSTED_OR_MISMATCHED_CHALLENGER_OUTPUT")
        cp = _probabilities(o.get("fulltime_probabilities"))
        trailing = "HOME" if state["home_goals"] < state["away_goals"] else (
            "AWAY" if state["away_goals"] < state["home_goals"] else None)
        _require(o.get("trailing_team") == trailing
                 and (o.get("trailing_team_comeback_win_probability") is None
                      if trailing is None else
                      type(o.get("trailing_team_comeback_win_probability")) in (int, float)
                      and abs(o["trailing_team_comeback_win_probability"] - cp[trailing]) <= 1e-7),
                 "CONTRADICTORY_COMEBACK_PROBABILITY")
        _require(all(type(o.get(k)) in (int, float) and math.isfinite(o[k])
                     and 0 <= o[k] <= 24
                     for k in ("remaining_expected_home_goals", "remaining_expected_away_goals")),
                 "INVALID_REMAINING_EXPECTED_GOALS")
        base = baseline["scenarios"][1]
        bp = {"HOME": base["home_win"], "DRAW": base["draw"], "AWAY": base["away_win"]}
        comparison = {"baseline_1x2": bp, "challenger_claimed_1x2": cp,
                      "challenger_minus_baseline": {
                          k: round(cp[k] - bp[k], 7) for k in SIDES}}
        return {**result, "status": "RESEARCH_ONLY",
                "reason": "MATCHED_CLAIMED_SNAPSHOT_NOT_EXECUTION_ATTESTATION",
                "fixture_id": fixture["fixture_id"],
                "decision_utc": _utc(state["as_of_utc"]).isoformat(),
                "comparison": comparison,
                "sensitivity_bands": [x["goal_rate_multiplier"]
                                      for x in baseline["scenarios"]],
                "claimed_single_snapshot_structural_match": True,
                "final_result_or_odds_used": False,
                "no_new_model_training": True}
    except (KeyError, ValueError, OverflowError, TypeError, AttributeError) as error:
        return {**result, "reason": str(error) or "INVALID_INPUT"}
