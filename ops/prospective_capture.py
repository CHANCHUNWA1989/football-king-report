"""Offline collector for prospective research evidence; no API/network access.

Capture raw provider bytes and attestations from a trusted upstream collector.
The result remains HOLD even when structural checks pass.
"""
import argparse
import json
from pathlib import Path
from .prospective_evidence_chain import (
    canonical_record_sha256, payload_sha256, validate_prospective_chain,
)


def assemble_capture(metadata, forecast_raw, odds_raw, result_raw, model_raw):
    if not isinstance(metadata, dict):
        raise ValueError("metadata object required")
    record = dict(metadata)
    for key, raw in (
        ("forecast_payload_sha256", forecast_raw),
        ("odds_payload_sha256", odds_raw),
        ("result_payload_sha256", result_raw),
        ("model_sha256", model_raw),
    ):
        record[key] = payload_sha256(raw)
    record["production_recommendations"] = "DISABLED"
    result = validate_prospective_chain(record)
    return {
        "schema": "football-king-prospective-capture-v1",
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "record": record,
        "record_sha256": canonical_record_sha256(record),
        "validation": result,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--forecast", required=True)
    parser.add_argument("--odds", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    metadata = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
    capture = assemble_capture(metadata, *(Path(p).read_bytes() for p in (
        args.forecast, args.odds, args.result, args.model
    )))
    target = Path(args.output)
    if target.exists():
        raise FileExistsError("capture must be append-only; output exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as stream:
        json.dump(capture, stream, sort_keys=True, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"status": "HOLD", "output": str(target),
                      "valid_evidence_chain": capture["validation"]["valid_evidence_chain"]}))


if __name__ == "__main__":
    main()
