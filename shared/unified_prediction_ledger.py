"""Shared research-only prediction ledger (stdlib only)."""
from datetime import datetime, timezone
import json
import math

REQUIRED = ("prediction_id", "system", "event_id", "created_at", "model_version", "market", "selection", "probability", "odds", "status")
SYSTEMS = {"football", "basketball", "quant"}
STATUSES = {"RESEARCH_ONLY", "HOLD"}

def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO 8601 string")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return dt.astimezone(timezone.utc)

def validate_prediction(row):
    if not isinstance(row, dict):
        raise ValueError("prediction must be an object")
    missing = [k for k in REQUIRED if k not in row]
    if missing:
        raise ValueError("missing: " + ",".join(missing))
    for key in ("prediction_id", "event_id", "model_version", "market", "selection"):
        if not isinstance(row[key], str) or not row[key].strip():
            raise ValueError("invalid " + key)
    if (not isinstance(row["system"], str) or not isinstance(row["status"], str)
            or row["system"] not in SYSTEMS or row["status"] not in STATUSES):
        raise ValueError("unknown system or unsafe status")
    _timestamp(row["created_at"])
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
    if _timestamp(actual_result_at) <= _timestamp(prediction["created_at"]):
        raise ValueError("settlement must follow prediction")
    if type(outcome) is not int or outcome not in (0, 1):
        raise ValueError("outcome must be integer 0 or 1")
    p = prediction["probability"]
    return {"prediction_id": prediction["prediction_id"], "brier": (p - outcome)**2, "correct_at_50pct": (p > .5) == bool(outcome), "status": "EVALUATED_RESEARCH_ONLY"}
