"""Paired baseline versus challenger scoring on identical held-out fixtures.

Retrospective research only; supplied forecasts are not independently attested.
"""
import math
from ops.private_soccerdata_frequency_baseline import evaluate_frequency_baseline


def compare_to_frequency_baseline(records, challenger_rows, *, min_train=30, test_days=7):
    baseline = evaluate_frequency_baseline(records, min_train=min_train, test_days=test_days)
    if baseline.get("reason") == "INSUFFICIENT_HOLDOUT":
        return {"status": "HOLD", "reason": "INSUFFICIENT_HOLDOUT",
                "production_recommendations": "DISABLED", "model_promoted": False}
    if not isinstance(challenger_rows, list) or not challenger_rows:
        raise ValueError("INVALID_CHALLENGER_COHORT")
    expected = {p["fixture_id"]: p for p in baseline["predictions"]}
    supplied = {}
    for row in challenger_rows:
        if not isinstance(row, dict) or set(row) != {"fixture_id", "outcome", "probabilities"}:
            raise ValueError("INVALID_CHALLENGER_ROW")
        key = row["fixture_id"]
        if not isinstance(key, str) or key in supplied or key not in expected:
            raise ValueError("CHALLENGER_FIXTURE_MISMATCH")
        if row["outcome"] != expected[key]["outcome"]:
            raise ValueError("CHALLENGER_OUTCOME_MISMATCH")
        probs = row["probabilities"]
        if (not isinstance(probs, dict) or set(probs) != {"H", "D", "A"}
                or any(type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 1
                       for v in probs.values())
                or abs(sum(probs.values()) - 1) > 1e-6):
            raise ValueError("INVALID_CHALLENGER_PROBABILITIES")
        supplied[key] = probs
    if set(supplied) != set(expected):
        raise ValueError("INCOMPLETE_PAIRED_HOLDOUT")
    n = len(expected)
    loss = sum(-math.log(max(supplied[k][p["outcome"]], 1e-15))
               for k, p in expected.items()) / n
    brier = sum(sum((supplied[k][o] - (o == p["outcome"])) ** 2
                    for o in ("H", "D", "A")) for k, p in expected.items()) / n
    return {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
            "fixture_count": n, "fold_count": baseline["fold_count"],
            "baseline": {"log_loss": baseline["log_loss"],
                         "multiclass_brier_score": baseline["multiclass_brier_score"]},
            "challenger": {"log_loss": round(loss, 6),
                           "multiclass_brier_score": round(brier, 6)},
            "log_loss_delta_challenger_minus_baseline": round(loss - baseline["log_loss"], 6),
            "brier_delta_challenger_minus_baseline": round(brier - baseline["multiclass_brier_score"], 6),
            "positive_ev_verified": False, "independent_provenance_verified": False,
            "model_promoted": False,
            "note": "Negative deltas favor challenger; forecast timing and training provenance not independently verified."}
