"""Local pre-kickoff 1X2 prediction ledger; research only, not tamper-proof."""
import json
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path

def _utc(value):
    if not isinstance(value, str):
        raise ValueError("Missing timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("Timezone required")
    return parsed.astimezone(timezone.utc)

def append_forecast(path, record):
    required = {"event_id", "forecast_at", "kickoff_at", "probabilities"}
    if not isinstance(record, dict) or set(record) != required:
        raise ValueError("Unexpected forecast fields")
    event_id = record["event_id"]
    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("Invalid event ID")
    if not _utc(record["forecast_at"]) < _utc(record["kickoff_at"]):
        raise ValueError("Forecast must precede kickoff")
    probabilities = record["probabilities"]
    if not isinstance(probabilities, dict) or set(probabilities) != {"H", "D", "A"}:
        raise ValueError("Expected 1X2 probabilities")
    if any(type(p) not in (int, float) or not isfinite(p) or not 0 <= p <= 1
           for p in probabilities.values()) or abs(sum(probabilities.values())-1) > 1e-6:
        raise ValueError("Invalid probabilities")
    destination = Path(path)
    if destination.exists():
        with destination.open(encoding="utf-8") as source:
            for line in source:
                previous = json.loads(line)
                if previous["event_id"] == event_id:
                    raise ValueError("Duplicate forecast event")
    with destination.open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
    return {"mode": "research", "saved": True, "real_betting_enabled": False}
