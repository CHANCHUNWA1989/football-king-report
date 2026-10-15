"""Convert archived uncalibrated shadow predictions into audit-compatible research rows.

Never fetches live data, invents settlement, or upgrades model validation.
"""
import argparse
import json
import math
from pathlib import Path
from shadow_1x2_scoring import stamp

MODEL_SOURCE = "football-king-poisson-shrinkage-v4.1"


def convert(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get("schema") != "football-king-uncalibrated-shadow-1":
        raise ValueError("INVALID_SHADOW_SCHEMA")
    if snapshot.get("production_recommendations") != "DISABLED":
        raise ValueError("UNSAFE_SHADOW_SNAPSHOT")
    predictions = snapshot.get("predictions")
    if not isinstance(predictions, list) or len(predictions) > 10000:
        raise ValueError("INVALID_PREDICTIONS")
    if snapshot.get("predictions_count") != len(predictions):
        raise ValueError("PREDICTION_COUNT_MISMATCH")
    if snapshot.get("status") not in ("SHADOW_ONLY", "HOLD"):
        raise ValueError("INVALID_SHADOW_STATUS")
    captured = stamp(snapshot["as_of_utc"])
    seen = set()
    output = []
    for row in predictions:
        if not isinstance(row, dict) or not isinstance(row.get("event_id"), str) or not row["event_id"].strip():
            raise ValueError("INVALID_EVENT")
        event_id = row["event_id"]
        if event_id in seen:
            raise ValueError("DUPLICATE_EVENT")
        seen.add(event_id)
        forecast = stamp(row["prediction_utc"])
        kickoff = stamp(row["kickoff_utc"])
        if forecast != captured or forecast >= kickoff:
            raise ValueError("FORECAST_TIME_LEAKAGE_OR_CAPTURE_MISMATCH")
        if row.get("model") != "poisson-shrinkage-unvalidated-v4.1" or row.get("calibrated") is not False:
            raise ValueError("UNEXPECTED_MODEL")
        if row.get("production_recommendations") != "DISABLED":
            raise ValueError("UNSAFE_PREDICTION")
        probabilities = [row.get(k) for k in ("p_home", "p_draw", "p_away")]
        if any(type(p) not in (int, float) or not math.isfinite(p) or p < 0 or p > 1 for p in probabilities):
            raise ValueError("INVALID_PROBABILITIES")
        if abs(sum(probabilities) - 1) > 0.0001:
            raise ValueError("UNNORMALIZED_PROBABILITIES")
        output.append({
            "event_id": event_id, "forecast_utc": row["prediction_utc"],
            "kickoff_utc": row["kickoff_utc"], "source": MODEL_SOURCE,
            "p_home": probabilities[0], "p_draw": probabilities[1],
            "p_away": probabilities[2], "model": row["model"],
            "training_observations_sha256": row.get("training_observations_sha256"),
            "probabilities_are_no_vig_consensus": False,
            "prediction_or_value_bet": True,
            "independently_verified": False,
            "production_recommendations": "DISABLED",
        })
    return output


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    rows = convert(json.loads(Path(args.input).read_text(encoding="utf-8")))
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"research_forecasts": len(rows), "settlements_verified": 0,
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
