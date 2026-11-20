"""Offline evaluation of already-timestamped football totals probabilities.

Input CSV must contain prediction_time, kickoff_time, home_goals,
away_goals, predicted_over_2_5. No network, bookmaker odds, or model fitting.
"""
import argparse
import csv
import datetime as dt
import json
import math
from pathlib import Path

FIELDS = ("prediction_time", "kickoff_time", "home_goals", "away_goals", "predicted_over_2_5")


def _parse_time(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return parsed


def evaluate(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)) or not set(FIELDS).issubset(reader.fieldnames):
            raise ValueError("INVALID_PREDICTION_COLUMNS")
        rows = list(reader)
    valid = []
    rejected = 0
    for row in rows:
        try:
            prediction_time, kickoff_time = _parse_time(row["prediction_time"]), _parse_time(row["kickoff_time"])
            hg, ag = int(row["home_goals"]), int(row["away_goals"])
            probability = float(row["predicted_over_2_5"])
            if not prediction_time < kickoff_time or hg < 0 or ag < 0 or not math.isfinite(probability) or not 0 < probability < 1:
                raise ValueError("INVALID_ROW")
            valid.append((probability, int(hg + ag > 2)))
        except (ValueError, TypeError, KeyError, OverflowError):
            rejected += 1
    if not valid:
        return {"status": "HOLD", "valid_rows": 0, "rejected_rows": rejected,
                "reason": "NO_VALID_PREMATCH_PREDICTIONS", "production_recommendations": "DISABLED"}
    n = len(valid)
    brier = sum((p - y) ** 2 for p, y in valid) / n
    logloss = -sum(y * math.log(p) + (1 - y) * math.log(1 - p) for p, y in valid) / n
    accuracy = sum((p >= 0.5) == bool(y) for p, y in valid) / n
    return {"status": "OFFLINE_EVALUATION_ONLY", "valid_rows": n, "rejected_rows": rejected,
            "brier": round(brier, 6), "log_loss": round(logloss, 6),
            "threshold_accuracy": round(accuracy, 6),
            "roi": None, "positive_ev_verified": False, "production_recommendations": "DISABLED",
            "warning": "Timestamps are syntactically checked, not independently authenticated; provenance and out-of-sample separation require external verification."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("predictions_csv")
    args = parser.parse_args()
    print(json.dumps(evaluate(args.predictions_csv), sort_keys=True))


if __name__ == "__main__":
    main()
