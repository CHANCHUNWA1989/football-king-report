"""Offline adapter for explicitly approved openfootball-style match results.

Accepts locally provided JSON only. No downloading, training, or market odds.
Input: list of matches with score.ft: [home, away] and round/date optional.
"""
import json
from pathlib import Path


def evaluate_openfootball_json(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("matches"), list):
        return {"status": "HOLD", "reason": "INVALID_MATCH_COLLECTION"}
    totals = {"over_2_5": 0, "under_2_5": 0, "draw": 0}
    skipped = 0
    for match in data["matches"]:
        if not isinstance(match, dict):
            skipped += 1
            continue
        score = match.get("score")
        ft = score.get("ft") if isinstance(score, dict) else None
        if not isinstance(ft, list) or len(ft) != 2 or any(type(x) is not int or x < 0 for x in ft):
            skipped += 1
            continue
        totals["over_2_5" if sum(ft) >= 3 else "under_2_5"] += 1
        totals["draw"] += int(ft[0] == ft[1])
    valid = totals["over_2_5"] + totals["under_2_5"]
    if not valid:
        return {"status": "HOLD", "reason": "NO_VALID_MATCHES", "skipped_rows": skipped}
    return {"status": "SCORE_ONLY_RESEARCH", "valid_matches": valid, "skipped_rows": skipped,
            **totals, "over_2_5_rate": round(totals["over_2_5"] / valid, 6),
            "odds_available": False, "roi_available": False,
            "model_predictions_evaluated": 0, "production_recommendations": "DISABLED"}
