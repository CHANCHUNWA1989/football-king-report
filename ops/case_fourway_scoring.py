"""Score one unchanged paired forecast against an unverified FT candidate.

This pure function does not authenticate evidence or write a settlement ledger.
Its caller must freshly verify and bind the original forecast/capture bytes.
The A/B/C and market vectors remain exactly as supplied by that sealed pair.
"""
from datetime import datetime, timedelta, timezone
import math

from ops.model_ab import matches_sealed as sealed_b_valid
from ops.model_market_challenger import matches_sealed as sealed_c_valid
from ops.research_center import score as canonical_score
from ops.source_fixture_identity import validate_sealed_identity


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _text(value):
    return (type(value) is str and 0 < len(value) <= 512
            and value == value.strip()
            and not any(ord(character) < 32 or ord(character) == 127 for character in value))


def _utc(value):
    _require(type(value) is str and 0 < len(value) <= 100, "INVALID_PAIRED_CHRONOLOGY")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        _require(parsed.tzinfo is not None, "INVALID_PAIRED_CHRONOLOGY")
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("INVALID_PAIRED_CHRONOLOGY") from None


def _vector(values):
    # Bound values before isfinite so oversized integer claims cannot escape
    # as OverflowError. Match the existing score routine's sum tolerance.
    _require(type(values) is list and len(values) == 3
             and all(type(value) in (int, float) and 0 <= value <= 1
                     and math.isfinite(value) for value in values)
             and abs(sum(values) - 1) <= .002, "INVALID_PAIRED_PROBABILITIES")


def score_case(pair: dict, score_ft: list[int, int]) -> dict:
    """Return descriptive same-case losses; never admit a certified outcome."""
    _require(type(pair) is dict, "INVALID_PAIRED_CASE")
    _require(type(score_ft) is list and len(score_ft) == 2
             and all(type(goal) is int and 0 <= goal <= 30 for goal in score_ft),
             "INVALID_SCORE_FT_CANDIDATE")
    _require(pair.get("production_recommendations") == "DISABLED"
             and all(pair.get(field) is False for field in (
                 "independently_verified", "eligible_for_model_scoring", "available_for_betting"))
             and all(field in pair and pair[field] is None for field in ("result", "historical_outcome"))
             and all(pair.get(field) is None for field in ("score_ft", "y")),
             "UNSAFE_OR_RESULT_BEARING_PAIR")
    for field in ("eligible_for_betting_promotion", "results_independently_verified",
                  "outcomes_independently_authenticated", "result_verified", "ready_for_production",
                  "automatic_bets", "automatic_bets_allowed", "model_advantage_vs_market_proven",
                  "positive_ev_betting_confirmed", "actual_kickoff_independently_authenticated",
                  "regulation_90_minute_ft_authenticated"):
        _require(field not in pair or pair[field] is False, "UNSAFE_OR_RESULT_BEARING_PAIR")
    _require("certified_case_count" not in pair
             or (type(pair["certified_case_count"]) is int and pair["certified_case_count"] == 0),
             "UNSAFE_OR_RESULT_BEARING_PAIR")
    _require(all(_text(pair.get(field)) for field in (
        "case_id", "forecast_event_id", "market_event_id", "league", "home", "away"))
             and pair["home"].casefold() != pair["away"].casefold(), "INVALID_PAIRED_IDENTITY")
    try:
        validate_sealed_identity(pair)
    except (ValueError, TypeError, KeyError, OverflowError):
        raise ValueError("INVALID_PAIRED_IDENTITY") from None
    kickoff, prediction, snapshot, updated = (_utc(pair.get(field)) for field in (
        "kickoff_utc", "prediction_utc", "market_snapshot_utc", "market_updated_utc"))
    _require(updated <= snapshot <= prediction < kickoff
             and kickoff - prediction >= timedelta(minutes=10)
             and (snapshot - updated).total_seconds() <= 8 * 3600
             and (prediction - snapshot).total_seconds() <= 750 * 60,
             "INVALID_PAIRED_CHRONOLOGY")
    for field in ("model", "market", "ab", "c"):
        _vector(pair.get(field))
    _require(sealed_b_valid(pair["model"], pair["ab"], pair.get("ab_model")),
             "UNSEALED_B_CHALLENGER")
    _require(sealed_c_valid(pair["model"], pair["market"], pair["c"], pair.get("c_model"))
             and pair.get("c_uses_only_prior_de_vigged_market") is True
             and pair.get("c_research_only_not_calibrated_or_executable") is True,
             "UNSEALED_C_CHALLENGER")
    outcome = 0 if score_ft[0] > score_ft[1] else 1 if score_ft[0] == score_ft[1] else 2
    models = {}
    for name, field in (("A", "model"), ("B", "ab"), ("C", "c"), ("market", "market")):
        loss, brier = canonical_score(pair[field], outcome)
        models[name] = {"source_field": field, "probabilities": list(pair[field]),
                        "log_loss": loss, "brier": brier}
    # The pair supplies only model/market field provenance for A and market.
    # B/C have registered IDs already present in the original pair.
    models["B"]["model_id"] = pair["ab_model"]
    models["C"]["model_id"] = pair["c_model"]
    return {
        "schema": "football-king-case-fourway-score-candidate-v1",
        "status": "HOLD", "reason": "UNAUTHENTICATED_RESULT_CANDIDATE_ONLY",
        "production_recommendations": "DISABLED", "candidate_only": True,
        "certified_case_count": 0, "independently_verified": False,
        "eligible_for_model_scoring": False, "eligible_for_betting_promotion": False,
        "results_independently_verified": False, "model_advantage_vs_market_proven": False,
        "market_is_executable_price": False, "automatic_bets": False,
        "derived_review_not_a_trust_input": True,
        **{field: pair[field] for field in (
            "case_id", "forecast_event_id", "market_event_id", "league", "home", "away",
            "prediction_utc", "market_snapshot_utc", "market_updated_utc")},
        "recorded_kickoff_utc": pair["kickoff_utc"],
        "score_ft_candidate": list(score_ft), "y": outcome, "models": models,
    }
