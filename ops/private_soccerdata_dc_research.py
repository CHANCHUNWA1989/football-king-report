"""Retrospective Dixon-Coles low-score correction fitted on earlier-day results.

Applies the standard tau correction to an independently fitted historical
team-Poisson forecast. Rho is selected on training-only log likelihood.
No forecast-time verification, live odds or production recommendation.
"""
import math
from ops.private_soccerdata_team_poisson import evaluate_team_poisson
from ops.private_soccerdata_walk_forward import make_walk_forward_folds


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


def _estimate_rho(training, lh, la):
    # Restrict rho to safe range for low-scoring correction.
    best, score = 0.0, float("-inf")
    for step in range(-10, 11):
        rho = step / 100
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
        rho = _estimate_rho(training, lh, la)
        # Estimate a conservative low-score mass from training league rates.
        # This is a research approximation, not a full joint DC MLE refit.
        p0h, p1h = math.exp(-lh), lh * math.exp(-lh)
        p0a, p1a = math.exp(-la), la * math.exp(-la)
        delta_h = p1h * p0a * (la * rho) + p0h * p1a * (lh * rho)
        delta_d = p0h * p0a * (-lh * la * rho) + p1h * p1a * (-rho)
        original = p["probabilities"]
        corrected = {"H": original["H"] + p1h * p0a * la * rho,
                     "D": original["D"] + delta_d,
                     "A": original["A"] + p0h * p1a * lh * rho}
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
            "model": "approximate_low_score_dixon_coles_research_v1",
            "prediction_count": n, "fold_count": folds["fold_count"],
            "log_loss": round(loss, 6), "multiclass_brier_score": round(brier, 6),
            "predictions": predictions, "independent_provenance_verified": False,
            "positive_ev_verified": False, "model_promoted": False,
            "note": "Approximate low-score correction with training-only league rho, not full DC joint MLE."}
