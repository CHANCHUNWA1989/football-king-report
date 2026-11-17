"""Retrospective Dixon-Coles low-score correction fitted on earlier-day results.

Applies the standard tau correction to an independently fitted historical
team-Poisson forecast. Rho is selected on training-only log likelihood.
No forecast-time verification, live odds or production recommendation.
"""
import math
from ops.private_soccerdata_team_poisson import evaluate_team_poisson, _fit_goal_rates
from ops.private_soccerdata_walk_forward import make_walk_forward_folds

MODEL = "approximate_low_score_dixon_coles_conditional_rho_v5"


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


def _rho_scores(training, rate_pairs):
    """Profile conditional training likelihood at each admissible grid point."""
    if not isinstance(rate_pairs, (list, tuple)) or len(rate_pairs) != len(training):
        raise ValueError("INVALID_RHO_RATE_PROFILE")
    try:
        if any(not isinstance(pair, (list, tuple)) or len(pair) != 2
               or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in pair)
               for pair in rate_pairs):
            raise ValueError("INVALID_RHO_RATE_PROFILE")
    except OverflowError:
        raise ValueError("INVALID_RHO_RATE_PROFILE") from None
    unique_rates = set(tuple(pair) for pair in rate_pairs)
    scores = {}
    for step in range(-10, 11):
        rho = step / 100
        factors = [_tau(h, a, home_rate, away_rate, rho)
                   for home_rate, away_rate in unique_rates
                   for h, a in ((0, 0), (0, 1), (1, 0), (1, 1))]
        if any(not math.isfinite(v) or v <= 0 for v in factors):
            continue
        values = [_tau(r["home_goals"], r["away_goals"], home_rate, away_rate, rho)
                  for r, (home_rate, away_rate) in zip(training, rate_pairs)]
        if any(not math.isfinite(v) or v <= 0 for v in values):
            continue
        scores[rho] = math.fsum(math.log(v) for v in values)
    return scores


def _select_rho(scores, prediction_rates=None):
    # Neutral tau gives log likelihood zero; strict improvements alone win.
    best, score = 0.0, 0.0
    for rho, candidate in scores.items():
        if prediction_rates is not None:
            factors = [_tau(h, a, *prediction_rates, rho) for h, a in ((0, 0), (0, 1), (1, 0), (1, 1))]
            if any(not math.isfinite(v) or v <= 0 for v in factors):
                continue
        if candidate > score:
            best, score = rho, candidate
    return best


def _estimate_rho(training, lh, la, *, prediction_rates=None, training_rates=None):
    """Compatibility helper; real fits supply a matched rate pair per training row."""
    rates = [(lh, la)] * len(training) if training_rates is None else training_rates
    return _select_rho(_rho_scores(training, rates), prediction_rates)


def evaluate_dixon_coles_correction(records, *, min_train=30, test_days=7):
    poisson = evaluate_team_poisson(records, min_train=min_train, test_days=test_days)
    if poisson["status"] != "RESEARCH_ONLY":
        return {"status": "HOLD", "reason": "INSUFFICIENT_HOLDOUT",
                "production_recommendations": "DISABLED", "model_promoted": False}
    folds = make_walk_forward_folds(records, min_train=min_train, test_days=test_days)
    indexed = {r["source_index"]: r for r in records}
    predictions = []
    profiles = {}
    for p in poisson["predictions"]:
        fold_index = p["fold_index"]
        if fold_index not in profiles:
            fold = folds["folds"][fold_index]
            training = [indexed[k] for k in fold["train_ids"]]
            fitted_rates = _fit_goal_rates(training)
            rates = [fitted_rates(r["home_team"], r["away_team"]) for r in training]
            profiles[fold_index] = _rho_scores(training, rates)
        target_home, target_away = p["expected_home_goals"], p["expected_away_goals"]
        rho = _select_rho(profiles[fold_index], (target_home, target_away))
        # Transfer mass in the same normalized score grid as the target base.
        # Conditional rho fitting is two-stage, not joint DC MLE.
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
            "rho_likelihood_basis": "FITTED_TRAINING_MATCH_RATES",
            "prediction_count": n, "fold_count": folds["fold_count"],
            "log_loss": round(loss, 6), "multiclass_brier_score": round(brier, 6),
            "predictions": predictions, "independent_provenance_verified": False,
            "positive_ev_verified": False, "model_promoted": False,
            "note": "Two-stage conditional rho on earlier fitted training-match rates, with target-rate feasibility. Not joint DC MLE or authenticated OOS evidence."}
