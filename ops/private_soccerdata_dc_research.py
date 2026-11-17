"""Retrospective Dixon-Coles low-score correction fitted on earlier-day results.

Applies the standard tau correction to an independently fitted historical
team-Poisson forecast. Rho is selected on training-only log likelihood.
No forecast-time verification, live odds or production recommendation.
"""
import math
from ops.private_soccerdata_team_poisson import evaluate_team_poisson
from ops.private_soccerdata_walk_forward import make_walk_forward_folds

MODEL = "approximate_low_score_dixon_coles_fixture_rate_v4"


def _tau(h, a, lh, la, rho):
    if h == 0 and a == 0:
        return 1 - lh * la * rho
    if h == 0 and a == 1:
        return 1 + lh * rho
    if h == 1 and a == 0:
        return 1 + la * rho
    if h == 1 and a == 1:
        return 1 - rho
    return 1.0


def _estimate_rho(training, lh, la, *, prediction_rates=None):
    """Training likelihood selects rho; fitted target rates only bound feasibility."""
    # Restrict rho to safe range for low-scoring correction.
    # At rho=0 every tau is one, so training log likelihood is exactly zero.
    # Keep that neutral model when no candidate strictly improves it.
    best, score = 0.0, 0.0
    rate_pairs = [(lh, la)]
    if prediction_rates is not None:
        rate_pairs.append(prediction_rates)
    for step in range(-10, 11):
        rho = step / 100
        factors = [_tau(h, a, home_rate, away_rate, rho)
                   for home_rate, away_rate in rate_pairs
                   for h, a in ((0, 0), (0, 1), (1, 0), (1, 1))]
        if any(not math.isfinite(v) or v <= 0 for v in factors):
            continue
        values = [_tau(r["home_goals"], r["away_goals"], lh, la, rho)
                  for r in training]
        if any(v <= 0 for v in values):
            continue
        candidate = sum(math.log(v) for v in values)
        if candidate > score:
            best, score = rho, candidate
    return best


def evaluate_dixon_coles_correction(records, *, min_train=30, test_days=7):
    poisson = evaluate_team_poisson(records, min_train=min_train, test_days=test_days)
    if poisson["status"] != "RESEARCH_ONLY":
        return {"status": "HOLD", "reason": "INSUFFICIENT_HOLDOUT",
                "production_recommendations": "DISABLED", "model_promoted": False}
    folds = make_walk_forward_folds(records, min_train=min_train, test_days=test_days)
    indexed = {r["source_index"]: r for r in records}
    predictions = []
    for p in poisson["predictions"]:
        fold = folds["folds"][p["fold_index"]]
        training = [indexed[k] for k in fold["train_ids"]]
        lh = max(sum(r["home_goals"] for r in training) / len(training), .05)
        la = max(sum(r["away_goals"] for r in training) / len(training), .05)
        target_home, target_away = p["expected_home_goals"], p["expected_away_goals"]
        rho = _estimate_rho(training, lh, la, prediction_rates=(target_home, target_away))
        # Transfer mass in the same normalized score grid as the target base.
        # Rho likelihood still uses training league rates, not joint DC MLE.
        changes = {f"{h}-{a}": p["low_score_probabilities"][f"{h}-{a}"]
                   * (_tau(h, a, target_home, target_away, rho) - 1)
                   for h, a in ((0, 0), (0, 1), (1, 0), (1, 1))}
        original = p["probabilities"]
        corrected = {"H": original["H"] + changes["1-0"],
                     "D": original["D"] + changes["0-0"] + changes["1-1"],
                     "A": original["A"] + changes["0-1"]}
        if any(not math.isfinite(v) or v < 0 for v in corrected.values()):
            raise ValueError("INVALID_DC_CORRECTION")
        total = sum(corrected.values())
        corrected = {k: v / total for k, v in corrected.items()}
        predictions.append({**p, "probabilities": corrected, "training_only_rho": rho})
    n = len(predictions)
    loss = sum(-math.log(max(p["probabilities"][p["outcome"]], 1e-15)) for p in predictions) / n
    brier = sum(sum((p["probabilities"][k] - (k == p["outcome"])) ** 2
                    for k in ("H", "D", "A")) for p in predictions) / n
    return {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
            "model": MODEL,
            "base_model": poisson["model"],
            "prediction_count": n, "fold_count": folds["fold_count"],
            "log_loss": round(loss, 6), "multiclass_brier_score": round(brier, 6),
            "predictions": predictions, "independent_provenance_verified": False,
            "positive_ev_verified": False, "model_promoted": False,
            "note": "Target-rate/grid low-score correction; rho likelihood uses earlier training league rates with target-rate feasibility. Not joint DC MLE."}
