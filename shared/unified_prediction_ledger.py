"""Shared fail-closed prediction ledger schema, stdlib only."""
from datetime import datetime, timezone
import json
import math

REQUIRED = ("prediction_id", "system", "event_id", "created_at", "model_version", "market", "selection", "probability", "odds", "status")
SYSTEMS = {"football", "basketball", "quant"}
STATUSES = {"RESEARCH_ONLY", "HOLD"}

def validate_prediction(row):
    if not isinstance(row, dict):
        raise ValueError("prediction must be an object")
    missing = [k for k in REQUIRED if k not in row]
    if missing:
        raise ValueError("missing: " + ",".join(missing))
    for key in ("prediction_id", "event_id", "model_version", "market", "selection"):
        if not isinstance(row[key], str) or not row[key].strip():
            raise ValueError("invalid " + key)
    if row["system"] not in SYSTEMS or row["status"] not in STATUSES:
        raise ValueError("unknown system or unsafe status")
    dt = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    p = row["probability"]
    if isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1:
        raise ValueError("invalid probability")
    odds = row["odds"]
    if odds is not None and (isinstance(odds, bool) or not isinstance(odds, (int, float)) or not math.isfinite(odds) or odds <= 1):
        raise ValueError("invalid decimal odds")
    return True

def record_prediction(path, row):
    validate_prediction(row)
    with open(path, "a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")

def settle_prediction(prediction, outcome, actual_result_at):
    validate_prediction(prediction)
    dt = datetime.fromisoformat(actual_result_at.replace("Z", "+00:00"))
    created = datetime.fromisoformat(prediction["created_at"].replace("Z", "+00:00"))
    if dt.tzinfo is None or dt <= created:
        raise ValueError("settlement must follow prediction")
    if outcome not in (0, 1):
        raise ValueError("outcome must be 0 or 1")
    p = prediction["probability"]
    return {"prediction_id": prediction["prediction_id"], "brier": (p - outcome)**2, "correct_at_50pct": (p > .5) == bool(outcome), "status": "EVALUATED_RESEARCH_ONLY"}
