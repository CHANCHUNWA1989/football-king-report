"""Offline prospective forecast receipt: immutable, research-only, no odds or picks."""
import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path


def _utc(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_TIMESTAMP")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return dt.astimezone(timezone.utc)


def seal(payload, *, now=None):
    if not isinstance(payload, dict) or set(payload) != {
        "schema", "source_namespace", "fixture_id", "kickoff_utc",
        "as_of_utc", "model_id", "model_version", "probabilities",
        "production_recommendations"
    } or payload["schema"] != "football-king-forecast-seal-input-v1":
        raise ValueError("INVALID_CONTRACT")
    for field in ("source_namespace", "fixture_id", "model_id", "model_version"):
        val = payload[field]
        if not isinstance(val, str) or not val or len(val) > 128 or val != val.strip():
            raise ValueError("INVALID_ID")
    if payload["production_recommendations"] != "DISABLED":
        raise ValueError("PRODUCTION_NOT_DISABLED")
    kickoff, as_of = _utc(payload["kickoff_utc"]), _utc(payload["as_of_utc"])
    captured = datetime.now(timezone.utc) if now is None else now
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("CAPTURE_TIMEZONE_REQUIRED")
    captured = captured.astimezone(timezone.utc)
    if not as_of <= captured < kickoff:
        raise ValueError("NOT_PROSPECTIVE")
    probs = payload["probabilities"]
    if not isinstance(probs, list) or len(probs) != 3 or any(
        type(x) not in (float, int) or not math.isfinite(x) or not 0 <= x <= 1
        for x in probs
    ) or abs(sum(probs) - 1) > 1e-6:
        raise ValueError("INVALID_PROBABILITIES")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return {
        "schema": "football-king-forecast-receipt-v1",
        "status": "RESEARCH_ONLY",
        "capture_utc": captured.isoformat(),
        "payload_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "forecast": payload,
        "independently_timestamped": False,
        "source_authenticity_verified": False,
        "production_recommendations": "DISABLED",
        "positive_ev_verified": False,
    }


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if Path(args.input).resolve() == Path(args.output).resolve():
        raise ValueError("INPUT_OUTPUT_ALIAS")
    with open(args.input, encoding="utf-8") as fh:
        payload = json.load(fh, object_pairs_hook=_unique_pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))
    receipt = seal(payload)
    data = (json.dumps(receipt, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    print(json.dumps({"status": "RESEARCH_ONLY", "sha256": receipt["payload_sha256"],
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
