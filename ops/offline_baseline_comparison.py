"""Paired held-out Brier comparison against an independently supplied baseline.

Requires predictions for identical settled events. No betting or EV output.
"""
import math
from offline_temporal_split import split_historical_forecasts
from offline_calibration_report import evaluate_binary_calibration


def compare_heldout_baseline(rows, *, test_fraction=0.2, embargo_hours=24):
    hold = {"status": "HOLD", "reason": "UNVERIFIED_BASELINE_COMPARISON",
            "production_recommendations": "DISABLED"}
    split = split_historical_forecasts(
        rows, test_fraction=test_fraction, embargo_hours=embargo_hours)
    if split["status"] != "RESEARCH_ONLY":
        return hold
    test_ids = set(split["test_event_ids"])
    heldout = [row for row in rows if row.get("event_id") in test_ids]
    model_rows = []
    baseline_rows = []
    for row in heldout:
        baseline = row.get("baseline_probability")
        if (type(baseline) not in (int, float) or not math.isfinite(baseline)
                or not 0 <= baseline <= 1):
            return hold
        model_rows.append({"event_id": row["event_id"],
                           "probability": row.get("probability"),
                           "outcome": row.get("outcome")})
        baseline_rows.append({"event_id": row["event_id"],
                              "probability": baseline,
                              "outcome": row.get("outcome")})
    model = evaluate_binary_calibration(model_rows)
    base = evaluate_binary_calibration(baseline_rows)
    if model["status"] != "RESEARCH_ONLY" or base["status"] != "RESEARCH_ONLY":
        return hold
    delta = round(model["brier_score"] - base["brier_score"], 6)
    return {"status": "RESEARCH_ONLY", "reason": "PAIRED_HELDOUT_BRIER_COMPARISON",
            "test_count": len(heldout), "model_brier": model["brier_score"],
            "baseline_brier": base["brier_score"], "brier_delta": delta,
            "model_better_on_sample": delta < 0,
            "source_authenticity_verified": False, "model_validated": False,
            "positive_ev_verified": False, "production_recommendations": "DISABLED"}
