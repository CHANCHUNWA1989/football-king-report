"""Capture a pre-match research snapshot before results exist.

Offline, append-only and fail-closed. Timestamps are supplied by upstream
collectors; a local digest does not independently authenticate capture time.
"""
import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from .prospective_evidence_chain import canonical_record_sha256, payload_sha256
from .frozen_forecast_join import join_historical_envelope


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


def capture_market_inputs(metadata, forecast_raw, odds_raw, model_raw):
    """Bind existing frozen-forecast JSON to an offline historical odds envelope.

    Input forecasts use frozen_forecast_join's list contract, not reconstructed
    1X2 forecasts. Metadata records the source/license reference and actual
    receipt times separately from the provider snapshot. These are declared
    provenance, not independent proof of rights, time, identity or tradability.
    Keep the original input files; SHA256 binds their exact bytes.
    """
    capture = capture_pre_match(metadata, forecast_raw, odds_raw, model_raw)
    for field in ("source_provider", "source_url", "license_reference"):
        if not isinstance(metadata.get(field), str) or not metadata[field].strip():
            raise ValueError("missing " + field)
    source = urlparse(metadata["source_url"])
    if (metadata["source_provider"] != "the_odds_api"
        or source.scheme != "https" or source.hostname != "api.the-odds-api.com"
        or source.username or source.password or source.query or source.fragment):
        raise ValueError("unrecognized or unsafe odds source URL")
    # Preserve the provider's decimal price text instead of rounding via float.
    forecasts, envelope = json.loads(forecast_raw), json.loads(odds_raw, parse_float=str)
    if not isinstance(envelope, dict) or not isinstance(envelope.get("data"), list):
        raise ValueError("raw bookmaker envelope required; 1X2 consensus is not odds")
    if not isinstance(forecasts, list) or not all(isinstance(f, dict) for f in forecasts):
        raise ValueError("frozen forecast list required; do not reconstruct 1X2 forecasts")
    matches = [f for f in forecasts if f.get("event_id") == metadata["event_id"]]
    if len(matches) != 1:
        raise ValueError("missing or duplicate frozen forecast event")
    forecast = matches[0]
    for field in ("kickoff_at", "kickoff_utc"):
        if field in forecast and _time(forecast[field]) != _time(metadata["kickoff_utc"]):
            raise ValueError("frozen forecast kickoff mismatch")
    provider_id = forecast.get("provider_event_id", forecast["event_id"])
    if provider_id != metadata["provider_event_id"]:
        raise ValueError("forecast/provider event identity mismatch")
    model_sha = forecast.get("model_artifact_sha256")
    if (forecast.get("model_version") != metadata["model_version"]
        or not isinstance(model_sha, str)
        or model_sha.lower() != capture["record"]["model_sha256"]):
        raise ValueError("forecast model version or artifact SHA256 mismatch")
    created = _time(forecast.get("created_at"))
    frozen = _time(metadata["forecast_captured_utc"])
    snapshot = _time(envelope.get("timestamp"))
    received = _time(metadata["odds_captured_utc"])
    if not created <= frozen <= snapshot <= received < _time(metadata["kickoff_utc"]):
        raise ValueError("invalid forecast/snapshot/receipt chronology")
    # Scope by explicit provider ID only. Never infer a bridge from team names.
    scoped = dict(envelope, data=[e for e in envelope["data"]
                                  if isinstance(e, dict) and e.get("id") == provider_id])
    if len(scoped["data"]) != 1:
        raise ValueError("missing or duplicate provider event")
    if _time(scoped["data"][0].get("commence_time")) != _time(metadata["kickoff_utc"]):
        raise ValueError("forecast/provider kickoff mismatch")
    quotes = join_historical_envelope(
        scoped, [dict(forecast, event_id=provider_id)], None)
    quotes = [q for q in quotes if q["bookmaker"] == metadata["bookmaker"]
              and q["market"] == metadata["market"]]
    if not quotes:
        raise ValueError("missing raw bookmaker quotes for requested market")
    # Recheck age at real receipt, not just at the historical snapshot time.
    for quote in quotes:
        for field in ("bookmaker_last_update", "market_last_update"):
            if (received - _time(quote[field])).total_seconds() > 30 * 60:
                raise ValueError("stale quote at actual receipt")
    capture["record"].update({
        "source_provider": metadata["source_provider"],
        "source_url": metadata["source_url"],
        "license_reference": metadata["license_reference"],
        "provider_snapshot_utc": envelope["timestamp"],
        "forecast_created_at": forecast["created_at"],
        "quotes": quotes,
        "input_binding": "STRUCTURAL_ONLY",
        "quotes_are_executable": False,
    })
    capture["record_sha256"] = canonical_record_sha256(capture["record"])
    return capture


def main():
    parser = argparse.ArgumentParser()
    for name in ("metadata", "forecast", "odds", "model", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--bind-market-inputs", action="store_true",
                        help="validate frozen forecasts and raw bookmaker envelope before capture")
    args = parser.parse_args()
    metadata = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
    capture_fn = capture_market_inputs if args.bind_market_inputs else capture_pre_match
    capture = capture_fn(metadata, Path(args.forecast).read_bytes(),
                         Path(args.odds).read_bytes(), Path(args.model).read_bytes())
    if args.bind_market_inputs:
        capture["record"]["source_files"] = {
            name: getattr(args, name) for name in ("forecast", "odds", "model")}
        capture["record_sha256"] = canonical_record_sha256(capture["record"])
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(capture, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps({"status": "HOLD", "record_sha256": capture["record_sha256"]}))


if __name__ == "__main__":
    main()
