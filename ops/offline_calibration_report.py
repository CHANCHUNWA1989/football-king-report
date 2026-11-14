"""Offline binary probability calibration diagnostics for historical forecasts.

Only evaluate settled, time-ordered predictions; this is not an EV engine.
Inputs must be curated by the caller to avoid leakage and duplicated events.
"""
import math


def evaluate_binary_calibration(rows, *, bins=10):
    hold = {"status": "HOLD", "reason": "INSUFFICIENT_VALIDATED_HISTORY",
            "production_recommendations": "DISABLED"}
    if not isinstance(rows, list) or len(rows) < 30 or len(rows) > 100000:
        return hold
    if type(bins) is not int or not 2 <= bins <= 20:
        return hold
    seen = set()
    buckets = [{"count": 0, "predicted_sum": 0.0, "observed_sum": 0} for _ in range(bins)]
    brier_sum = 0.0
    for row in rows:
        if not isinstance(row, dict):
            return hold
        event, p, y = row.get("event_id"), row.get("probability"), row.get("outcome")
        if (not isinstance(event, str) or not event.strip() or event in seen
                or type(p) not in (float, int) or not math.isfinite(p)
                or not 0 <= p <= 1 or type(y) is not int or y not in (0, 1)):
            return hold
        seen.add(event)
        bucket = min(int(p * bins), bins - 1)
        buckets[bucket]["count"] += 1
        buckets[bucket]["predicted_sum"] += p
        buckets[bucket]["observed_sum"] += y
        brier_sum += (p - y) ** 2
    calibration = [
        {"bin": i, "count": b["count"],
         "mean_predicted": round(b["predicted_sum"] / b["count"], 5),
         "observed_rate": round(b["observed_sum"] / b["count"], 5)}
        for i, b in enumerate(buckets) if b["count"]
    ]
    return {"status": "RESEARCH_ONLY", "reason": "OFFLINE_CALIBRATION_DIAGNOSTIC",
            "sample_count": len(rows), "brier_score": round(brier_sum / len(rows), 6),
            "calibration_bins": calibration, "production_recommendations": "DISABLED",
            "positive_ev_verified": False}
