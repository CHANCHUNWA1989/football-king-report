"""Retrospective expanding-window 1X2 frequency baseline from MatchHistory.

No external data fetch, no odds, no timestamp attestation, no Poisson/DC claim.
Laplace smoothing avoids zero-probability outcomes on sparse samples.
"""
import math
from ops.private_soccerdata_walk_forward import make_walk_forward_folds


def evaluate_frequency_baseline(records, *, min_train=30, test_days=7, smoothing=1.0):
    if type(smoothing) not in (int, float) or not math.isfinite(smoothing) or smoothing <= 0:
        raise ValueError("INVALID_SMOOTHING")
    folds = make_walk_forward_folds(records, min_train=min_train, test_days=test_days)
    outcomes = {r["source_index"]: r["outcome"] for r in records}
    if len(outcomes) != len(records):
        raise ValueError("DUPLICATE_SOURCE_INDEX")
    predictions = []
    for i, fold in enumerate(folds["folds"]):
        train = fold["train_ids"]
        counts = {k: sum(outcomes[x] == k for x in train) for k in ("H", "D", "A")}
        total = len(train) + 3 * smoothing
        probabilities = {k: (counts[k] + smoothing) / total for k in ("H", "D", "A")}
        for key in fold["test_ids"]:
            predictions.append({"fixture_id": key, "fold_index": i,
                                "outcome": outcomes[key], "probabilities": probabilities.copy(),
                                "training_match_count": len(train)})
    if not predictions:
        return {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
                "reason": "INSUFFICIENT_HOLDOUT", "fold_count": 0,
                "prediction_count": 0, "positive_ev_verified": False,
                "independent_provenance_verified": False}
    n = len(predictions)
    log_loss = -sum(math.log(p["probabilities"][p["outcome"]]) for p in predictions) / n
    brier = sum(sum((p["probabilities"][k] - (p["outcome"] == k)) ** 2
                    for k in ("H", "D", "A")) for p in predictions) / n
    return {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
            "model": "laplace_smoothed_historical_frequency_baseline",
            "fold_count": folds["fold_count"], "prediction_count": n,
            "log_loss": round(log_loss, 6), "multiclass_brier_score": round(brier, 6),
            "predictions": predictions, "positive_ev_verified": False,
            "independent_provenance_verified": False, "model_promoted": False,
            "note": "Retrospective local-day splits only. Not a pre-match verified or bookmaker EV backtest."}
