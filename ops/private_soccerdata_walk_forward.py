"""Strict walk-forward cohort preparation from independently timestamped match rows.

Never train on same-day matches: MatchHistory source-local timestamps are not
independently authenticated kickoff instants. Train only on earlier calendar days.
"""
from datetime import date, datetime


def make_walk_forward_folds(records, *, min_train=30, test_days=7):
    if not isinstance(records, list) or not records:
        raise ValueError("INVALID_HISTORY")
    if type(min_train) is not int or min_train < 2 or type(test_days) is not int or test_days < 1:
        raise ValueError("INVALID_FOLD_SETTINGS")
    by_day = {}
    seen = set()
    for row in records:
        if not isinstance(row, dict) or row.get("source") != "soccerdata.MatchHistory" or row.get("kickoff_time_verified") is not False or row.get("pre_match_features_verified") is not False:
            raise ValueError("UNVERIFIED_HISTORY_RECORD")
        key = row.get("source_index")
        stamp = row.get("source_local_match_datetime")
        if not isinstance(key, str) or not key or key in seen or not isinstance(stamp, str):
            raise ValueError("INVALID_HISTORY_ID_OR_DATE")
        seen.add(key)
        # Parse the ENTIRE timestamp. Prefix-only date parsing incorrectly
        # accepted impossible dates such as 2026-01-01T99:99:99.
        if len(stamp) != 19 or stamp[10] != "T":
            raise ValueError("UNTRUSTED_TIMEZONE")
        try:
            parsed = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S")
        except ValueError as exc:
            raise ValueError("INVALID_HISTORY_DATE") from exc
        if parsed.strftime("%Y-%m-%dT%H:%M:%S") != stamp:
            raise ValueError("INVALID_HISTORY_DATE")
        day = parsed.date()
        if row.get("outcome") not in ("H", "D", "A"):
            raise ValueError("INVALID_OUTCOME")
        by_day.setdefault(day, []).append(key)
    days = sorted(by_day)
    folds = []
    for start in range(1, len(days), test_days):
        train_days = days[:start]
        train = [k for day in train_days for k in by_day[day]]
        if len(train) < min_train:
            continue
        holdout_days = days[start:start + test_days]
        test = [k for day in holdout_days for k in by_day[day]]
        folds.append({"train_ids": train, "test_ids": test,
                      "train_last_local_day": train_days[-1].isoformat(),
                      "test_first_local_day": holdout_days[0].isoformat()})
    return {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
            "folds": folds, "fold_count": len(folds),
            "independently_verified_kickoff": False,
            "models_fitted": False, "point_in_time_backtest_ready": False,
            "note": "Calendar-day leakage guard only; upstream source timestamps and availability are not independently attested."}
