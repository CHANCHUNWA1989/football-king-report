"""Capture a pre-match research snapshot before results exist.

Offline, append-only and fail-closed. Timestamps are supplied by upstream
collectors; a local digest does not independently authenticate capture time.
"""
import argparse
import json
from datetime import datetime
from pathlib import Path
from .prospective_evidence_chain import canonical_record_sha256, payload_sha256


def _time(value):
    if not isinstance(value, str):
        raise ValueError("missing timestamp")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("naive timestamp")
    return dt


def capture_pre_match(metadata, forecast_raw, odds_raw, model_raw):
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")
    for key in ("event_id", "provider_event_id", "model_version",
                "market", "bookmaker", "forecast_source_commit"):
        if not isinstance(metadata.get(key), str) or not metadata[key].strip():
            raise ValueError("missing " + key)
    forecast = _time(metadata.get("forecast_captured_utc"))
    odds = _time(metadata.get("odds_captured_utc"))
    kickoff = _time(metadata.get("kickoff_utc"))
    if not (forecast < kickoff and odds < kickoff):
        raise ValueError("snapshot not pre-match")
    record = {k: metadata[k] for k in (
        "event_id", "provider_event_id", "model_version", "market",
        "bookmaker", "forecast_source_commit", "forecast_captured_utc",
        "odds_captured_utc", "kickoff_utc")}
    record.update({
        "model_sha256": payload_sha256(model_raw),
        "forecast_payload_sha256": payload_sha256(forecast_raw),
        "odds_payload_sha256": payload_sha256(odds_raw),
        "production_recommendations": "DISABLED",
    })
    return {
        "schema": "football-king-prematch-evidence-v1",
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "outcome_status": "NOT_YET_SETTLED",
        "source_independently_attested": False,
        "record": record,
        "record_sha256": canonical_record_sha256(record),
    }


def main():
    parser = argparse.ArgumentParser()
    for name in ("metadata", "forecast", "odds", "model", "output"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    metadata = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
    capture = capture_pre_match(metadata, Path(args.forecast).read_bytes(),
                                Path(args.odds).read_bytes(), Path(args.model).read_bytes())
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(capture, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps({"status": "HOLD", "record_sha256": capture["record_sha256"]}))


if __name__ == "__main__":
    main()
