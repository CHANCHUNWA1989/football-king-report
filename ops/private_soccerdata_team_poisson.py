"""Expanding-window retrospective team-goal Poisson model, offline research only.

Fits league and team scoring rates using strictly earlier local calendar days.
No kickoff verification, no bookmaker odds, no EV or production promotion.
"""
import math
from ops.private_soccerdata_walk_forward import make_walk_forward_folds

MODEL = "retrospective_team_goal_poisson_adaptive_tail_v2"
MAX_EXPECTED_GOALS = 15
POISSON_TAIL_MASS_BOUND = 1e-12
MAX_GOAL_SUPPORT = 256
DEFAULT_SHRINKAGE = 5.0


def _poisson(lam, maximum=12):
    """Extend beyond the legacy cutoff until the omitted tail is bounded.

    After endpoint k, later PMF ratios are <= lam/(k+2), so the remaining
    mass is <= P(k+1)/(1-lam/(k+2)) once that ratio is below one.
    Normalize the retained PMF; never move all missing mass into one score.
    """
    if type(lam) not in (int, float) or not 0 <= lam <= MAX_EXPECTED_GOALS:
        raise ValueError("INVALID_POISSON_RATE")
    if type(maximum) is not int or not 0 <= maximum <= MAX_GOAL_SUPPORT:
        raise ValueError("INVALID_POISSON_CUTOFF")
    p = [math.exp(-lam)]
    for k in range(MAX_GOAL_SUPPORT + 1):
        next_probability = p[-1] * lam / (k + 1)
        ratio = lam / (k + 2)
        if (k >= maximum and ratio < 1
                and next_probability / (1 - ratio) <= POISSON_TAIL_MASS_BOUND):
            total = math.fsum(p)
            return [value / total for value in p]
        p.append(next_probability)
    raise ValueError("POISSON_TAIL_NOT_BOUNDED")


def _fit_goal_rates(training, *, shrinkage=DEFAULT_SHRINKAGE):
    """Fit the existing role-specific shrinkage model once; return its rate function."""
    home_mean = max(sum(r["home_goals"] for r in training) / len(training), .05)
    away_mean = max(sum(r["away_goals"] for r in training) / len(training), .05)
    home_scored, home_conceded, away_scored, away_conceded = {}, {}, {}, {}
    def add(store, team, goals):
        total, count = store.get(team, (0, 0))
        store[team] = (total + goals, count + 1)
    for r in training:
        add(home_scored, r["home_team"], r["home_goals"])
        add(home_conceded, r["home_team"], r["away_goals"])
        add(away_scored, r["away_team"], r["away_goals"])
        add(away_conceded, r["away_team"], r["home_goals"])
    def rate(store, team, prior):
        total, count = store.get(team, (0, 0))
        return (total + shrinkage * prior) / (count + shrinkage)
    def predict(home_team, away_team):
        home_lambda = home_mean * (rate(home_scored, home_team, home_mean) / home_mean) * (rate(away_conceded, away_team, home_mean) / home_mean)
        away_lambda = away_mean * (rate(away_scored, away_team, away_mean) / away_mean) * (rate(home_conceded, home_team, away_mean) / away_mean)
        return min(home_lambda, MAX_EXPECTED_GOALS), min(away_lambda, MAX_EXPECTED_GOALS)
    return predict


def evaluate_team_poisson(records, *, min_train=30, test_days=7, shrinkage=DEFAULT_SHRINKAGE):
    if type(shrinkage) not in (float, int) or not math.isfinite(shrinkage) or shrinkage <= 0:
        raise ValueError("INVALID_SHRINKAGE")
    folds = make_walk_forward_folds(records, min_train=min_train, test_days=test_days)
    indexed = {r["source_index"]: r for r in records}
    if len(indexed) != len(records):
        raise ValueError("DUPLICATE_HISTORY_ID")
    for r in records:
        if (not isinstance(r.get("home_team"), str) or not r["home_team"].strip()
                or not isinstance(r.get("away_team"), str) or not r["away_team"].strip()
                or r["home_team"] == r["away_team"]
                or any(type(r.get(k)) is not int or not 0 <= r[k] <= 30
                       for k in ("home_goals", "away_goals"))
                or r["outcome"] != ("H" if r["home_goals"] > r["away_goals"]
                                    else "A" if r["home_goals"] < r["away_goals"] else "D")):
            raise ValueError("INVALID_SCORE_OR_TEAM")
    predictions = []
    for i, fold in enumerate(folds["folds"]):
        training = [indexed[k] for k in fold["train_ids"]]
        fitted_rates = _fit_goal_rates(training, shrinkage=shrinkage)
        for key in fold["test_ids"]:
            r = indexed[key]
            home_lambda, away_lambda = fitted_rates(r["home_team"], r["away_team"])
            hp, ap = _poisson(home_lambda), _poisson(away_lambda)
            probs = {"H": 0.0, "D": 0.0, "A": 0.0}
            for h, ph in enumerate(hp):
                for a, pa in enumerate(ap):
                    probs["H" if h > a else "A" if h < a else "D"] += ph * pa
            predictions.append({"fixture_id": key, "fold_index": i,
                                "outcome": r["outcome"], "probabilities": probs,
                                "expected_home_goals": home_lambda,
                                "expected_away_goals": away_lambda,
                                "low_score_probabilities": {
                                    "0-0": hp[0] * ap[0], "0-1": hp[0] * ap[1],
                                    "1-0": hp[1] * ap[0], "1-1": hp[1] * ap[1]},
                                "training_match_count": len(training)})
    if not predictions:
        return {"status": "HOLD", "reason": "INSUFFICIENT_HOLDOUT",
                "production_recommendations": "DISABLED", "prediction_count": 0}
    n = len(predictions)
    loss = sum(-math.log(max(p["probabilities"][p["outcome"]], 1e-15)) for p in predictions) / n
    brier = sum(sum((p["probabilities"][k] - (k == p["outcome"])) ** 2
                    for k in ("H", "D", "A")) for p in predictions) / n
    return {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
            "model": MODEL, "fold_count": folds["fold_count"],
            "per_team_omitted_tail_mass_bound": POISSON_TAIL_MASS_BOUND,
            "prediction_count": n, "log_loss": round(loss, 6),
            "multiclass_brier_score": round(brier, 6), "predictions": predictions,
            "independent_provenance_verified": False, "positive_ev_verified": False,
            "model_promoted": False}
