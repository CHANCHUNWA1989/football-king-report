"""Reproducible offline historical O/U 2.5 baseline from an existing local CSV.

No network requests. This is a market-implied baseline, not an AI forecast.
"""
import argparse
import csv
import json
import math
from pathlib import Path

from ops.historical_total_2_5_settlement import settle_total_2_5, flat_stake_profit

REQUIRED = ("Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "B365>2.5", "B365<2.5")


def analyze_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not set(REQUIRED).issubset(reader.fieldnames):
            raise ValueError("MISSING_REQUIRED_COLUMNS")
        rows = list(reader)
    total = 0
    brier_sum = 0.0
    logloss_sum = 0.0
    skipped = 0
    for row in rows:
        try:
            hg, ag = int(row["FTHG"]), int(row["FTAG"])
            over, under = float(row["B365>2.5"]), float(row["B365<2.5"])
            if hg < 0 or ag < 0 or not all(math.isfinite(x) and 1.01 <= x <= 500 for x in (over, under)):
                raise ValueError("BAD_VALUES")
            implied_over, implied_under = 1 / over, 1 / under
            probability = implied_over / (implied_over + implied_under)
            outcome = int(settle_total_2_5(hg, ag, "Over") == "WIN")
            brier_sum += (probability - outcome) ** 2
            logloss_sum += -(outcome * math.log(probability) + (1 - outcome) * math.log(1 - probability))
            total += 1
        except (ValueError, TypeError, KeyError, OverflowError):
            skipped += 1
    if not total:
        return {"status": "HOLD", "reason": "NO_VALID_ROWS", "valid_rows": 0, "skipped_rows": skipped}
    return {"status": "HISTORICAL_BASELINE_ONLY", "valid_rows": total, "skipped_rows": skipped,
            "brier": round(brier_sum / total, 6), "log_loss": round(logloss_sum / total, 6),
            "model_predictions_evaluated": 0, "positive_ev_verified": False,
            "production_recommendations": "DISABLED"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", help="Existing local CSV; never downloaded by this script")
    args = parser.parse_args()
    print(json.dumps(analyze_csv(args.csv_path), sort_keys=True))


if __name__ == "__main__":
    main()
