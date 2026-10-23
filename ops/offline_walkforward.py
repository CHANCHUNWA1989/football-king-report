"""Expanding-window walk-forward audit for pre-match historical forecasts.

No model fitting is performed. Each fold evaluates pre-recorded forecasts only;
training records must have settled before the test window's first prediction.
"""
from datetime import datetime, timedelta, timezone
from offline_calibration_report import evaluate_binary_calibration


def _utc(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else None


def evaluate_walkforward(rows, *, min_train=60, test_size=30,
                         step_size=30, embargo_hours=24):
    hold = {"status": "HOLD", "reason": "INVALID_WALKFORWARD_HISTORY",
            "production_recommendations": "DISABLED"}
    if (not isinstance(rows, list) or len(rows) > 100000
            or any(type(x) is not int for x in
                   (min_train, test_size, step_size, embargo_hours))
            or min_train < 30 or test_size < 30 or step_size < test_size
            or embargo_hours < 0 or embargo_hours > 720
            or len(rows) < min_train + test_size):
        return hold
    checked = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            return hold
        event = row.get("event_id")
        predicted = _utc(row.get("predicted_at_utc"))
        kickoff = _utc(row.get("kickoff_at_utc"))
        settled = _utc(row.get("settled_at_utc"))
        if (not isinstance(event, str) or not event.strip() or event in seen
                or predicted is None or kickoff is None or settled is None
                or not predicted < kickoff < settled):
            return hold
        seen.add(event)
        checked.append((predicted, settled, row))
    if any(checked[i][0] > checked[i + 1][0] for i in range(len(checked) - 1)):
        return hold
    folds = []
    for start in range(min_train, len(checked) - test_size + 1, step_size):
        test = checked[start:start + test_size]
        cutoff = test[0][0] - timedelta(hours=embargo_hours)
        train = [item for item in checked[:start] if item[1] < cutoff]
        if len(train) < min_train:
            continue
        score = evaluate_binary_calibration(
            [{"event_id": item[2]["event_id"],
              "probability": item[2].get("probability"),
              "outcome": item[2].get("outcome")} for item in test])
        if score["status"] != "RESEARCH_ONLY":
            return hold
        folds.append({"fold": len(folds) + 1, "train_count": len(train),
                      "test_count": len(test), "test_brier": score["brier_score"],
                      "test_event_ids": [item[2]["event_id"] for item in test]})
    if len(folds) < 2:
        return hold
    return {"status": "RESEARCH_ONLY", "reason": "EXPANDING_WINDOW_DIAGNOSTIC",
            "fold_count": len(folds), "folds": folds,
            "mean_fold_brier": round(sum(f["test_brier"] for f in folds) / len(folds), 6),
            "source_authenticity_verified": False, "model_validated": False,
            "positive_ev_verified": False, "production_recommendations": "DISABLED"}
