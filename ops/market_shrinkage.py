"""Conservative market shrinkage candidate and chronological validation.

Research-only: compare on future holdout; never claim improvement from fitting
weights to the same settled matches or enable production recommendations.
"""
import math
from datetime import datetime, timezone


def validate_probs(p):
    if not isinstance(p, (list, tuple)) or len(p) != 3:
        raise ValueError("INVALID_PROBABILITIES")
    if any(type(x) not in (int, float) or not math.isfinite(x) or x < 0 or x > 1 for x in p):
        raise ValueError("INVALID_PROBABILITIES")
    if abs(sum(p) - 1) > 0.002:
        raise ValueError("INVALID_PROBABILITIES")


def ranked_probability_score(probabilities, outcome):
    """Normalized RPS in home/draw/away order; lower is better.

    Cumulative-outcome algorithm adapted from penaltyblog metrics, Copyright
    2021 Martin Eastwood (MIT); source/permission: third_party/penaltyblog/.
    Accepted rounding residuals are normalized locally without changing inputs.
    No numeric coercion, model promotion or profitability certification.
    """
    validate_probs(probabilities)
    if type(outcome) is not int or outcome not in (0, 1, 2):
        raise ValueError("INVALID_OUTCOME")
    mass = sum(probabilities)
    probabilities = [probability / mass for probability in probabilities]
    cumulative = total = 0.0
    for index, probability in enumerate(probabilities):
        cumulative += probability
        total += (cumulative - int(outcome <= index)) ** 2
    return total / (len(probabilities) - 1)


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
    ll = brier = rps = hits = 0.0
    for row in rows:
        p = blend(row["p"], row["m"], weight)
        y = row["y"]
        if type(y) is not int or y not in (0, 1, 2):
            raise ValueError("INVALID_OUTCOME")
        ll -= math.log(max(p[y], 1e-15))
        brier += sum((p[j] - (j == y)) ** 2 for j in range(3))
        rps += ranked_probability_score(p, y)
        hits += int(max(range(3), key=lambda j: p[j]) == y)
    n = len(rows)
    return {"n": n, "log_loss": ll / n, "brier": brier / n,
            "rps": rps / n, "accuracy": hits / n}


def _kickoff_key(row):
    """UTC ordering key; legacy dates remain unauthenticated day labels.

    This never replaces a recorded timestamp or authenticates pre-match data.
    """
    value = row["kickoff"]
    try:
        if isinstance(value, str):
            date_only = len(value) == 10
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if date_only:
                value = value.replace(tzinfo=timezone.utc)
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timezone-aware kickoff required")
        return value.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("INVALID_KICKOFF") from exc


def compare(rows, holdout_fraction=0.25):
    """Fixed weights on a UTC-ordered holdout, with disjoint kickoff cohorts.

    No models are fitted here; a valid split still does not establish OOS proof.
    """
    if not isinstance(rows, list):
        raise ValueError("INVALID_ROWS")
    ordered = sorted(rows, key=_kickoff_key)
    split = max(1, int(len(ordered) * (1 - holdout_fraction)))
    if (split < len(ordered)
            and _kickoff_key(ordered[split - 1]) == _kickoff_key(ordered[split])):
        raise ValueError("TRAIN_HOLDOUT_BOUNDARY_SHARED_KICKOFF")
    holdout = ordered[split:]
    results = {f"{w:.2f}": score(holdout, w) for w in (0, 0.5, 0.75, 1)}
    # Small or short-span retrospective samples are descriptive, not evidence of superiority.
    weeks = {_kickoff_key(r).date() for r in holdout}
    enough_for_screening = len(holdout) >= 300 and len(weeks) >= 84
    return {
        "status": "RESEARCH_ONLY" if enough_for_screening else "HOLD",
        "reason": "RETROSPECTIVE_SCREENING_ONLY" if enough_for_screening else "INSUFFICIENT_HOLDOUT_EVIDENCE",
        "holdout_screening_threshold_matches": 300,
        "holdout_screening_threshold_distinct_dates": 84,
        "holdout_distinct_dates": len(weeks),
        "total": len(ordered),
        "holdout_n": len(holdout),
        "holdout_is_independent_forward_sample": False,
        "candidate_weights_predeclared": [0, 0.5, 0.75, 1],
        "holdout_comparison": results,
        "evaluation_metrics": ["log_loss", "brier", "rps", "accuracy"],
        "market_baseline_weight": 1.0,
        "production_recommendations": "DISABLED",
        "warning": "Exploratory retrospective chronological holdout only; no verified forward evidence.",
    }
