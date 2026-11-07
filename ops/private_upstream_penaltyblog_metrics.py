"""Use the upstream penaltyblog ranked probability score implementation.

Dependency integration, not a rewritten or copied upstream implementation.
For football 1X2 the required outcome order is H, D, A.
"""
import math


def score_ranked_1x2(rows):
    if not isinstance(rows, list) or not rows or len(rows) > 2500:
        raise ValueError("INVALID_RPS_COHORT")
    probabilities, outcomes = [], []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"probabilities", "outcome"}:
            raise ValueError("INVALID_RPS_ROW")
        p = row["probabilities"]
        if not isinstance(p, dict) or set(p) != {"H", "D", "A"} or row["outcome"] not in ("H", "D", "A"):
            raise ValueError("INVALID_RPS_TARGET")
        values = [p[k] for k in ("H", "D", "A")]
        if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in values) or abs(sum(values)-1) > 1e-6:
            raise ValueError("INVALID_RPS_PROBABILITIES")
        probabilities.append(values)
        outcomes.append(("H", "D", "A").index(row["outcome"]))
    try:
        from penaltyblog.metrics import rps_average
    except ImportError as exc:
        raise ValueError("OPTIONAL_PENALTYBLOG_NOT_INSTALLED") from exc
    result = float(rps_average(probabilities, outcomes))
    if not math.isfinite(result) or result < 0:
        raise ValueError("INVALID_UPSTREAM_RPS_RESULT")
    return {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
            "metric": "ranked_probability_score", "upstream": "martineastwood/penaltyblog",
            "fixture_count": len(rows), "rps": round(result, 8),
            "positive_ev_verified": False, "model_promoted": False}
