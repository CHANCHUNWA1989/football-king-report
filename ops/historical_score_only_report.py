"""Offline score-only evaluator for licensed match-result exports.

Input is an existing local CSV with Date, HomeTeam, AwayTeam, FTHG, FTAG.
No network access, no market odds and no AI predictions are implied.
"""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def evaluate_results(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)) or not required.issubset(reader.fieldnames):
            return {"status": "HOLD", "reason": "INVALID_HEADERS"}
        rows = list(reader)
    seen = set()
    totals = Counter()
    for row in rows:
        key = tuple((row.get(field) or "").strip() for field in ("Date", "HomeTeam", "AwayTeam"))
        if not all(key) or key[1] == key[2] or key in seen:
            return {"status": "HOLD", "reason": "INVALID_OR_DUPLICATE_FIXTURE"}
        seen.add(key)
        try:
            home, away = int(row["FTHG"]), int(row["FTAG"])
            if home < 0 or away < 0:
                raise ValueError()
        except (TypeError, ValueError, KeyError):
            return {"status": "HOLD", "reason": "INVALID_SCORE"}
        totals["over_2_5" if home + away >= 3 else "under_2_5"] += 1
        totals["home_win" if home > away else "draw" if home == away else "away_win"] += 1
    if not rows:
        return {"status": "HOLD", "reason": "EMPTY_DATASET"}
    return {"status": "SCORE_ONLY_RESEARCH", "matches": len(rows),
            "over_2_5": totals["over_2_5"], "under_2_5": totals["under_2_5"],
            "over_2_5_rate": round(totals["over_2_5"] / len(rows), 6),
            "home_wins": totals["home_win"], "draws": totals["draw"], "away_wins": totals["away_win"],
            "ai_predictions_evaluated": 0, "roi_available": False,
            "production_recommendations": "DISABLED"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    args = parser.parse_args()
    print(json.dumps(evaluate_results(args.csv_path), sort_keys=True))


if __name__ == "__main__":
    main()
