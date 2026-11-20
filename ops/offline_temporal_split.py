"""Deterministic chronological train/test split for offline football research.

This is a split audit, not model training or a claim of predictive performance.
"""
from datetime import datetime, timezone


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo is not None else None


def split_historical_forecasts(rows, *, test_fraction=0.2, embargo_hours=24):
    hold = {"status": "HOLD", "reason": "INVALID_TEMPORAL_SPLIT",
            "production_recommendations": "DISABLED"}
    if (not isinstance(rows, list) or not 50 <= len(rows) <= 100000
            or type(test_fraction) is not float or not 0.1 <= test_fraction <= 0.4
            or type(embargo_hours) is not int or not 0 <= embargo_hours <= 720):
        return hold
    checked = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            return hold
        event = row.get("event_id")
        predicted = _timestamp(row.get("predicted_at_utc"))
        kickoff = _timestamp(row.get("kickoff_at_utc"))
        settled = _timestamp(row.get("settled_at_utc"))
        if (not isinstance(event, str) or not event.strip() or event in seen
                or predicted is None or kickoff is None or settled is None
                or not predicted < kickoff < settled):
            return hold
        seen.add(event)
        checked.append((predicted, settled, event))
    if any(checked[i][0] > checked[i + 1][0] for i in range(len(checked) - 1)):
        return hold
    test_count = max(1, int(len(checked) * test_fraction))
    train, test = checked[:-test_count], checked[-test_count:]
    first_test_prediction = test[0][0]
    from datetime import timedelta
    cutoff = first_test_prediction - timedelta(hours=embargo_hours)
    eligible_train = [item for item in train if item[1] < cutoff]
    if len(eligible_train) < 30 or len(test) < 10:
        return hold
    return {
        "status": "RESEARCH_ONLY", "reason": "CHRONOLOGICAL_SPLIT_AUDITED",
        "train_event_ids": [item[2] for item in eligible_train],
        "test_event_ids": [item[2] for item in test],
        "excluded_train_count": len(train) - len(eligible_train),
        "train_count": len(eligible_train), "test_count": len(test),
        "embargo_hours": embargo_hours, "production_recommendations": "DISABLED",
        "model_validated": False,
    }
