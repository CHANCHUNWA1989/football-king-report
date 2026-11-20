"""Offline integrity checks for two research forecast receipts.

Accepts receipts shaped like PR #461's schema; never infers independent
timestamp attestation from a local clock or hash. Does not produce betting tips.
"""
import argparse
import hashlib
import json
import math
from datetime import datetime, timezone


def _timestamp(raw):
    if not isinstance(raw, str):
        raise ValueError("INVALID_TIMESTAMP")
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return value.astimezone(timezone.utc)


def _verify(receipt):
    if not isinstance(receipt, dict) or receipt.get("schema") != "football-king-forecast-receipt-v1":
        raise ValueError("INVALID_RECEIPT_SCHEMA")
    if receipt.get("status") != "RESEARCH_ONLY" or receipt.get("production_recommendations") != "DISABLED":
        raise ValueError("NOT_RESEARCH_ONLY")
    forecast = receipt.get("forecast")
    if not isinstance(forecast, dict) or set(forecast) != {
        "schema", "source_namespace", "fixture_id", "kickoff_utc",
        "as_of_utc", "model_id", "model_version", "probabilities",
        "production_recommendations"
    } or forecast["schema"] != "football-king-forecast-seal-input-v1":
        raise ValueError("INVALID_FORECAST")
    if forecast["production_recommendations"] != "DISABLED":
        raise ValueError("PRODUCTION_ENABLED")
    for key in ("source_namespace", "fixture_id", "model_id", "model_version"):
        if not isinstance(forecast[key], str) or not forecast[key] or forecast[key] != forecast[key].strip():
            raise ValueError("INVALID_ID")
    probs = forecast["probabilities"]
    if not isinstance(probs, list) or len(probs) != 3 or any(
        type(p) not in (int, float) or not math.isfinite(p) or p < 0 or p > 1 for p in probs
    ) or abs(sum(probs) - 1) > 1e-6:
        raise ValueError("INVALID_PROBABILITIES")
    canonical = json.dumps(forecast, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if receipt.get("payload_sha256") != digest:
        raise ValueError("HASH_MISMATCH")
    as_of = _timestamp(forecast["as_of_utc"])
    captured = _timestamp(receipt.get("capture_utc"))
    kickoff = _timestamp(forecast["kickoff_utc"])
    if not as_of <= captured < kickoff:
        raise ValueError("LOOKAHEAD_OR_INVALID_CAPTURE")
    return forecast, captured


def pair(left, right):
    try:
        a, captured_a = _verify(left)
        b, captured_b = _verify(right)
        keys = ("source_namespace", "fixture_id", "kickoff_utc", "as_of_utc")
        if any(a[key] != b[key] for key in keys):
            raise ValueError("NOT_SAME_FIXTURE_OR_CUTOFF")
        if a["model_id"] == b["model_id"] and a["model_version"] == b["model_version"]:
            raise ValueError("DUPLICATE_MODEL")
        if left.get("independently_timestamped") is not True or right.get("independently_timestamped") is not True:
            return {"status": "HOLD", "reason": "INDEPENDENT_TIMESTAMP_ATTESTATION_MISSING",
                    "local_hashes_valid": True, "same_fixture_and_cutoff": True,
                    "production_recommendations": "DISABLED"}
        # Caller-supplied attestation flags are NOT independently verified here.
        return {"status": "HOLD", "reason": "EXTERNAL_ATTESTATION_NOT_VERIFIED",
                "local_hashes_valid": True, "same_fixture_and_cutoff": True,
                "production_recommendations": "DISABLED"}
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        return {"status": "HOLD", "reason": str(exc),
                "production_recommendations": "DISABLED"}


def _unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("DUPLICATE_JSON_KEY")
        obj[key] = value
    return obj


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--left", required=True)
    parser.add_argument("--right", required=True)
    args = parser.parse_args()
    def read(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh, object_pairs_hook=_unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))
    print(json.dumps(pair(read(args.left), read(args.right)), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
