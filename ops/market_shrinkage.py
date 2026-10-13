"""Conservative market shrinkage candidate and chronological validation.

Research-only: compare on future holdout; never claim improvement from fitting
weights to the same settled matches or enable production recommendations.
"""
import math


def validate_probs(p):
    if not isinstance(p, (list, tuple)) or len(p) != 3:
        raise ValueError("INVALID_PROBABILITIES")
    if any(type(x) not in (int, float) or not math.isfinite(x) or x < 0 or x > 1 for x in p):
        raise ValueError("INVALID_PROBABILITIES")
    if abs(sum(p) - 1) > 0.002:
        raise ValueError("INVALID_PROBABILITIES")


def blend(model, market, market_weight=0.75):
    validate_probs(model)
    validate_probs(market)
    if type(market_weight) not in (int, float) or not math.isfinite(market_weight) or not 0 <= market_weight <= 1:
        raise ValueError("INVALID_WEIGHT")
    vals = [(1 - market_weight) * a + market_weight * b for a, b in zip(model, market)]
    total = sum(vals)
    return [v / total for v in vals]


def score(rows, weight):
    if not rows:
        return None
    ll = brier = hits = 0.0
    for row in rows:
        p = blend(row["p"], row["m"], weight)
        y = row["y"]
        if type(y) is not int or y not in (0, 1, 2):
            raise ValueError("INVALID_OUTCOME")
        ll -= math.log(max(p[y], 1e-15))
        brier += sum((p[j] - (j == y)) ** 2 for j in range(3))
        hits += int(max(range(3), key=lambda j: p[j]) == y)
    n = len(rows)
    return {"n": n, "log_loss": ll / n, "brier": brier / n, "accuracy": hits / n}


def compare(rows, holdout_fraction=0.25):
    """Fixed weight candidates on chronological holdout; no promotion."""
    if not isinstance(rows, list):
        raise ValueError("INVALID_ROWS")
    ordered = sorted(rows, key=lambda r: r["kickoff"])
    split = max(1, int(len(ordered) * (1 - holdout_fraction)))
    holdout = ordered[split:]
    results = {f"{w:.2f}": score(holdout, w) for w in (0, 0.5, 0.75, 1)}
    return {
        "status": "RESEARCH_ONLY" if holdout else "HOLD",
        "total": len(ordered),
        "holdout_n": len(holdout),
        "holdout_is_independent_forward_sample": False,
        "candidate_weights_predeclared": [0, 0.5, 0.75, 1],
        "holdout_comparison": results,
        "production_recommendations": "DISABLED",
        "warning": "Exploratory retrospective chronological holdout only; no verified forward evidence.",
    }
