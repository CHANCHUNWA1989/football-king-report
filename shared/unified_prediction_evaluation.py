"""Read-only research evaluation for verified binary outcomes."""
import json
from pathlib import Path
from shared.unified_prediction_ledger import validate_prediction, settle_prediction

def evaluate(predictions, outcomes):
    if not isinstance(predictions, list) or not isinstance(outcomes, list):
        raise ValueError("predictions and outcomes must be lists")
    if len(predictions) > 100000 or len(outcomes) > 100000:
        raise ValueError("evaluation input exceeds safety limit")
    by_id = {}
    groups = {}
    for row in predictions:
        validate_prediction(row)
        key = row["prediction_id"]
        if key in by_id:
            raise ValueError("duplicate prediction_id")
        by_id[key] = row
        group = groups.setdefault(row["system"], {"predictions": 0, "evaluated": 0, "pending": 0, "mean_brier": None})
        group["predictions"] += 1
    seen = set()
    scores = []
    group_scores = {key: [] for key in groups}
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
        score = settle_prediction(by_id[key], outcome.get("outcome"), outcome.get("actual_result_at"))
        seen.add(key)
        scores.append(score)
        group_scores[by_id[key]["system"]].append(score["brier"])
    for name, group in groups.items():
        values = group_scores[name]
        group["evaluated"] = len(values)
        group["pending"] = group["predictions"] - len(values)
        group["mean_brier"] = sum(values) / len(values) if values else None
    n = len(scores)
    return {
        "predictions": len(by_id),
        "evaluated": n,
        "pending": len(by_id) - n,
        "mean_brier": sum(s["brier"] for s in scores) / n if n else None,
        "correct_at_50pct": sum(s["correct_at_50pct"] is True for s in scores),
        "accuracy_denominator": sum(s["correct_at_50pct"] is not None for s in scores),
        "abstained_at_50pct": sum(s["correct_at_50pct"] is None for s in scores),
        "by_system": groups,
        "sample_warning": "INSUFFICIENT_VERIFIED_OUTCOMES" if n < 100 else None,
        "minimum_sample_for_reporting": 100,
        "research_only": True,
        "roi": None,
    }

def evaluate_jsonl(predictions_path, outcomes_path):
    def read(path):
        file = Path(path)
        if file.stat().st_size > 32_000_000:
            raise ValueError("evaluation file exceeds safety limit")
        with file.open(encoding="utf-8") as stream:
            rows = []
            for line in stream:
                if line.strip():
                    if len(rows) >= 100000:
                        raise ValueError("evaluation input exceeds safety limit")
                    rows.append(json.loads(line))
        return rows
    return evaluate(read(predictions_path), read(outcomes_path))
