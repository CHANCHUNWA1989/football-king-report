"""Offline out-of-sample calibration report with temporal embargo.

Evaluates only held-out events. Does not train models or validate source authenticity.
"""
from offline_temporal_split import split_historical_forecasts
from offline_calibration_report import evaluate_binary_calibration


def evaluate_heldout_calibration(rows, *, test_fraction=0.2, embargo_hours=24, bins=10):
    hold = {"status": "HOLD", "reason": "OUT_OF_SAMPLE_EVALUATION_UNAVAILABLE",
            "production_recommendations": "DISABLED"}
    split = split_historical_forecasts(
        rows, test_fraction=test_fraction, embargo_hours=embargo_hours)
    if split["status"] != "RESEARCH_ONLY":
        return {**hold, "split_reason": split["reason"]}
    test_ids = set(split["test_event_ids"])
    test_rows = [{"event_id": row.get("event_id"),
                  "probability": row.get("probability"),
                  "outcome": row.get("outcome")}
                 for row in rows if row.get("event_id") in test_ids]
    report = evaluate_binary_calibration(test_rows, bins=bins)
    if report["status"] != "RESEARCH_ONLY":
        return {**hold, "split_reason": "INSUFFICIENT_HELDOUT_CALIBRATION"}
    return {
        "status": "RESEARCH_ONLY", "reason": "HELDOUT_CALIBRATION_DIAGNOSTIC",
        "train_count": split["train_count"], "test_count": split["test_count"],
        "excluded_train_count": split["excluded_train_count"],
        "embargo_hours": embargo_hours,
        "heldout_brier_score": report["brier_score"],
        "heldout_calibration_bins": report["calibration_bins"],
        "source_authenticity_verified": False,
        "model_validated": False, "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
    }
