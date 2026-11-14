"""Canonical, tamper-evident research forecast snapshots.

Hash integrity is NOT independent proof of capture time or provider authenticity.
"""
import hashlib
import json
import math
from datetime import datetime


def _time(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_TIMESTAMP")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc
    if parsed.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return parsed


def _canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def seal(forecast):
    if not isinstance(forecast, dict) or set(forecast) != {
        "fixture_id", "model", "model_version", "prediction_utc",
        "kickoff_utc", "probabilities", "production_recommendations"
    }:
        raise ValueError("INVALID_SNAPSHOT_FIELDS")
    for field in ("fixture_id", "model_version"):
        if not isinstance(forecast[field], str) or not forecast[field] or len(forecast[field]) > 128:
            raise ValueError("INVALID_SNAPSHOT_ID")
    if forecast["model"] not in ("poisson", "dixon_coles") or forecast["production_recommendations"] != "DISABLED":
        raise ValueError("INVALID_RESEARCH_MODEL")
    if not _time(forecast["prediction_utc"]) < _time(forecast["kickoff_utc"]):
        raise ValueError("NOT_PREMATCH")
    probs = forecast["probabilities"]
    if not isinstance(probs, dict) or set(probs) != {"H", "D", "A"}:
        raise ValueError("INVALID_PROBABILITIES")
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 or v > 1 for v in probs.values()) or abs(sum(probs.values()) - 1) > 1e-6:
        raise ValueError("INVALID_PROBABILITIES")
    digest = hashlib.sha256(_canonical(forecast)).hexdigest()
    return {"schema": "football-king-research-forecast-snapshot-v1",
            "status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
            "capture_time_independently_attested": False,
            "provider_authenticity_verified": False,
            "forecast": forecast, "sha256": digest}


def verify(snapshot):
    if not isinstance(snapshot, dict) or set(snapshot) != {
        "schema", "status", "production_recommendations",
        "capture_time_independently_attested", "provider_authenticity_verified",
        "forecast", "sha256"
    } or snapshot["schema"] != "football-king-research-forecast-snapshot-v1" or snapshot["status"] != "RESEARCH_ONLY" or snapshot["production_recommendations"] != "DISABLED" or snapshot["capture_time_independently_attested"] is not False or snapshot["provider_authenticity_verified"] is not False:
        raise ValueError("INVALID_SNAPSHOT_ENVELOPE")
    sealed = seal(snapshot["forecast"])
    if not isinstance(snapshot["sha256"], str) or snapshot["sha256"] != sealed["sha256"]:
        raise ValueError("SNAPSHOT_TAMPERED")
    return True
