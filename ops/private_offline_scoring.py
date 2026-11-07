"""Offline scoring of sealed 1X2 predictions against independently supplied outcomes.

No provider authentication, betting claims, or model promotion. Aggregate only.
"""
import math

def score(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 2500:
        raise ValueError("INVALID_SCORING_COHORT")
    seen = set()
    logloss = brier = 0.0
    bins = [[0, 0.0, 0.0] for _ in range(10)]
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"fixture_id", "probabilities", "outcome", "prediction_utc", "kickoff_utc", "result_recorded_utc"}:
            raise ValueError("INVALID_SCORING_ROW")
        key = row["fixture_id"]
        if not isinstance(key, str) or not key or key in seen:
            raise ValueError("INVALID_OR_DUPLICATE_FIXTURE")
        seen.add(key)
        from ops.private_refit_forecast_adapter import _time
        pred, kickoff, result = (_time(row[k]) for k in ("prediction_utc", "kickoff_utc", "result_recorded_utc"))
        if not pred < kickoff < result:
            raise ValueError("LOOKAHEAD_OR_INVALID_RESULT_CHRONOLOGY")
        probs = row["probabilities"]
        if not isinstance(probs, dict) or set(probs) != {"H", "D", "A"} or any(type(v) not in (float, int) or not math.isfinite(v) or v < 0 or v > 1 for v in probs.values()) or abs(sum(probs.values()) - 1) > 1e-6:
            raise ValueError("INVALID_PROBABILITIES")
        outcome = row["outcome"]
        if outcome not in ("H", "D", "A"):
            raise ValueError("INVALID_OUTCOME")
        p = probs[outcome]
        logloss -= math.log(max(p, 1e-15))
        brier += sum((probs[k] - int(k == outcome)) ** 2 for k in ("H", "D", "A"))
        for k in ("H", "D", "A"):
            confidence = probs[k]
            bucket = min(int(confidence * 10), 9)
            bins[bucket][0] += 1
            bins[bucket][1] += confidence
            bins[bucket][2] += int(k == outcome)
    n = len(rows)
    calibration = [{"bin": i, "count": count, "mean_probability": round(total_p / count, 6), "observed_frequency": round(total_o / count, 6)} for i, (count, total_p, total_o) in enumerate(bins) if count]
    return {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED", "independent_provenance_verified": False, "positive_ev_verified": False, "fixture_count": n, "log_loss": round(logloss/n, 6), "multiclass_brier_score": round(brier/n, 6), "calibration": calibration}
