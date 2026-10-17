"""Offline research-only 1X2 probability diagnostics; never produces betting recommendations."""
import math

def _valid_probs(p):
    return (isinstance(p, (list, tuple)) and len(p) == 3
            and all(type(x) in (int, float) and math.isfinite(x) and 0 <= x <= 1 for x in p)
            and abs(sum(p) - 1) <= 1e-6)

def score_forecasts(rows):
    """Compute multiclass Brier and log loss; reject malformed or unsealed outcomes."""
    if not isinstance(rows, list) or len(rows) > 20000:
        raise ValueError("INVALID_SAMPLE_COUNT")
    if not rows:
        return {"n": 0, "brier": None, "log_loss": None, "status": "INSUFFICIENT_DATA", "production_recommendations": "DISABLED"}
    brier = logloss = 0.0
    for row in rows:
        if not isinstance(row, dict) or not _valid_probs(row.get("p")) or type(row.get("y")) is not int or row["y"] not in (0, 1, 2):
            raise ValueError("INVALID_FORECAST_SAMPLE")
        p, y = row["p"], row["y"]
        brier += sum((v - int(i == y)) ** 2 for i, v in enumerate(p))
        logloss -= math.log(max(p[y], 1e-15))
    n = len(rows)
    return {"n": n, "brier": brier / n, "log_loss": logloss / n, "status": "RESEARCH_ONLY", "production_recommendations": "DISABLED"}
