"""Side-by-side, *unverified* recency-weighted Penaltyblog research.

Does not modify the historical A/Poisson/DC snapshots, sealed records, or any
production pipeline. Weights are anchored to each target's as-of instant;
no outcome, betting price, or post-kickoff observation enters the fit.
"""
import argparse
import json
import math

from .penaltyblog_research_bridge import (
    SCHEMA as BASE_SCHEMA, MODELS, _timestamp, _validate, _unique_json, evaluate,
)

SCHEMA = "football-king-penaltyblog-time-decay-research-v1"
XI_PER_DAY = 0.003  # Fixed, unoptimised research hypothesis, NOT an OOS winner.


def _hold(reason, **extra):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "production_recommendations": "DISABLED", "positive_ev_verified": False,
        "model_promoted": False, "independent_provenance_verified": False,
        "source_authenticity_verified": False, "prospective_capture_verified": False,
        **extra,
    }


def compare(payload, *, model_factory=None):
    """Compare unweighted and pre-registered time-weighted fits on SAME input.

    Even successful fitting stays HOLD; numbers are diagnostic only.
    Optional model_factory is only for isolated synthetic tests.
    """
    required = {
        "schema", "production_recommendations", "model", "as_of_utc",
        "target_fixture", "historical_matches",
    }
    if (type(payload) is not dict or set(payload) != required
            or payload.get("schema") != SCHEMA
            or payload.get("production_recommendations") != "DISABLED"
            or payload.get("model") not in MODELS):
        return _hold("INVALID_CONTRACT")
    base = dict(payload)
    base["schema"] = BASE_SCHEMA
    try:
        _, rows = _validate(base)
        cutoff = _timestamp(payload["as_of_utc"])
        ages = [(cutoff - _timestamp(row["kickoff_utc"])).total_seconds() / 86400
                for row in rows]
        if not all(math.isfinite(age) and age > 0 for age in ages):
            return _hold("INVALID_TRAINING_AGE")
        weights = [math.exp(-XI_PER_DAY * age) for age in ages]
        if not all(math.isfinite(w) and 0 < w <= 1 for w in weights):
            return _hold("INVALID_DECAY_WEIGHTS")
    except (KeyError, TypeError, ValueError, OverflowError):
        return _hold("INVALID_OR_UNVERIFIED_INPUT")

    if model_factory is None:
        try:
            from penaltyblog import models
            model_factory = getattr(models, MODELS[payload["model"]])
        except (ImportError, AttributeError):
            return _hold("OPTIONAL_PENALTYBLOG_NOT_INSTALLED")

    original = evaluate(base, model_factory=model_factory)
    if original.get("status") != "RESEARCH_ONLY":
        return _hold("UNWEIGHTED_FIT_BLOCKED", model_reason=original.get("reason"))

    def weighted_factory(home_goals, away_goals, home_teams, away_teams):
        return model_factory(home_goals, away_goals, home_teams, away_teams,
                             weights=list(weights))

    weighted = evaluate(base, model_factory=weighted_factory)
    if weighted.get("status") != "RESEARCH_ONLY":
        return _hold("WEIGHTED_FIT_BLOCKED", model_reason=weighted.get("reason"))

    p0 = [original[key] for key in ("p_home", "p_draw", "p_away")]
    p1 = [weighted[key] for key in ("p_home", "p_draw", "p_away")]
    sum_weights = sum(weights)
    effective_n = sum_weights ** 2 / sum(w * w for w in weights)
    return _hold(
        "UNVERIFIED_MODEL_COMPARISON_ONLY",
        model_id=f"penaltyblog-{payload['model']}-time-decay-sidecar-v1",
        fixture_id=original["fixture_id"],
        as_of_utc=original["as_of_utc"],
        decay_xi_per_day=XI_PER_DAY,
        half_life_days=round(math.log(2) / XI_PER_DAY, 3),
        training_match_count=len(rows),
        effective_training_match_count=round(effective_n, 3),
        oldest_training_age_days=round(max(ages), 3),
        newest_training_age_days=round(min(ages), 3),
        unweighted_1x2=p0,
        weighted_1x2=p1,
        weighted_minus_unweighted_1x2=[round(b-a, 12) for a, b in zip(p0, p1)],
        note=("Research-only fixed xi, not tuned or proven superior. Source "
              "completeness, kickoff identity, bookmaker odds and OOS "
              "profitability remain unverified."),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline time-decay challenger HOLD")
    parser.add_argument("--input", required=True)
    args = parser.parse_args(argv)
    with open(args.input, encoding="utf-8") as fh:
        payload = json.load(
            fh, object_pairs_hook=_unique_json,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")),
        )
    print(json.dumps(compare(payload), ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
