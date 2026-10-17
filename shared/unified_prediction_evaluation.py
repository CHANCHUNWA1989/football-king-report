"""Read-only aggregate evaluation of previously recorded predictions.

Requires externally verified binary outcomes keyed by prediction_id.
Never infers a settlement from a forecast and never places orders.
"""
import json
from pathlib import Path
from shared.unified_prediction_ledger import validate_prediction, settle_prediction

def evaluate(predictions, outcomes):
    if not isinstance(predictions, list) or not isinstance(outcomes, list):
        raise ValueError("predictions and outcomes must be lists")
    by_id = {}
    for row in predictions:
        validate_prediction(row)
        key = row["prediction_id"]
        if key in by_id:
            raise ValueError("duplicate prediction_id")
        by_id[key] = row
    seen = set()
    scores = []
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            raise ValueError("invalid outcome")
        key = outcome.get("prediction_id")
        if not isinstance(key, str) or key not in by_id or key in seen:
            raise ValueError("unknown or duplicate outcome")
        if outcome.get("verified") is not True:
            raise ValueError("unverified outcome")
        if not isinstance(outcome.get("source"), str) or not outcome["source"].strip():
            raise ValueError("missing outcome source")
        seen.add(key)
        scores.append(settle_prediction(by_id[key], outcome.get("outcome"), outcome.get("actual_result_at")))
    n = len(scores)
    return {
        "predictions": len(by_id),
        "evaluated": n,
        "pending": len(by_id) - n,
        "mean_brier": sum(s["brier"] for s in scores) / n if n else None,
        "correct_at_50pct": sum(s["correct_at_50pct"] for s in scores),
        "research_only": True,
        "roi": None,
    }

def evaluate_jsonl(predictions_path, outcomes_path):
    def read(path):
        return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    return evaluate(read(predictions_path), read(outcomes_path))
