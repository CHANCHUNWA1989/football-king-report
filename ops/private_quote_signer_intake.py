"""Manual, public-safe prospective seal intake for GitHub Sigstore attestation.

Only a PRE-EXISTING, research-only, sanitized local seal JSON is admitted.
GitHub workflow_dispatch input and attestations in PUBLIC repositories are not
private transport: never include raw odds, provider responses, team names,
fixture IDs, model scorelines, API keys or secret material here.
This gate does NOT replay raw bookmaker evidence; the independent local
private_quote_seal_attestation verifier MUST still replay original private bytes
and verify the real Rekor time. This signer cannot award verified samples.
"""
import argparse
import base64
import binascii
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re

from private_quote_snapshot_receipt import _pairs_unique, _nonfinite
from private_quote_forward_freeze import SCHEMA as FREEZE_SCHEMA

SCHEMA = "football-king-private-prospective-signer-intake-v1"
MAX_SAFE_BYTES = 8192
MAX_BASE64_CHARS = ((MAX_SAFE_BYTES + 2) // 3) * 4
HASH = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")

SHA_FIELDS = frozenset((
    "raw_snapshot_sha256", "quote_receipt_sha256_unanchored",
    "fixture_market_binding_sha256_unanchored", "forecast_raw_bytes_sha256",
))
TIME_FIELDS = ("training_cutoff_utc_claimed", "prediction_utc_claimed",
               "kickoff_utc_claimed")
TRUE_FLAGS = frozenset(("raw_snapshot_binding_replayed",
                        "exact_fixture_and_line_structurally_matched",
                        "score_distribution_structurally_normalized"))
FALSE_FLAGS = frozenset((
    "training_data_leakage_independently_audited",
    "forecast_was_witnessed_before_kickoff",
    "fixture_source_independently_authenticated",
    "bookmaker_quote_independently_authenticated",
    "score_distribution_calibration_verified",
    "eligible_for_model_scoring", "executable_quote_verified",
    "model_edge_verified", "can_publish_pick",
))
ZERO_FIELDS = frozenset(("eligible_independently_verified_forward_samples",))
ALL_FIELDS = frozenset((
    "schema", "status", "forecast_raw_byte_count", "model_code_commit_claimed",
    "production_recommendations", "seal_sha256_unanchored",
)) | SHA_FIELDS | frozenset(TIME_FIELDS) | TRUE_FLAGS | FALSE_FLAGS | ZERO_FIELDS


class IntakeError(ValueError):
    """Constant reason only: never include user-supplied data in errors."""


def _require(condition, code):
    if not condition:
        raise IntakeError(code)


def _timestamp(value):
    _require(type(value) is str and 1 <= len(value) <= 80, "INVALID_CLAIMED_TIME")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        _require(instant.utcoffset() == timedelta(0)
                 and value == instant.astimezone(timezone.utc).isoformat(),
                 "INVALID_CLAIMED_TIME")
        return instant.astimezone(timezone.utc)
    except (ValueError, OverflowError, TypeError) as exc:
        raise IntakeError("INVALID_CLAIMED_TIME") from exc


def validate_sanitized_seal(safe_json_bytes, *, expected_sha256, now=None):
    """Return the EXACT input bytes for signing, never reserialize the subject.

    A forged but internally consistent seal remains possible. Neither the
    metadata nor the claimed capture/prediction clock is authenticated here.
    """
    _require(type(safe_json_bytes) is bytes and 0 < len(safe_json_bytes) <= MAX_SAFE_BYTES,
             "INVALID_SAFE_SEAL_BYTES")
    _require(type(expected_sha256) is str and HASH.fullmatch(expected_sha256) is not None,
             "INVALID_EXPECTED_DIGEST")
    digest = hashlib.sha256(safe_json_bytes).hexdigest()
    _require(hmac.compare_digest(digest, expected_sha256), "SEAL_BYTES_DIGEST_MISMATCH")
    try:
        document = json.loads(safe_json_bytes, object_pairs_hook=_pairs_unique,
                              parse_constant=_nonfinite)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise IntakeError("INVALID_SAFE_SEAL_JSON") from exc
    _require(type(document) is dict and set(document) == ALL_FIELDS, "UNSAFE_SEAL_FIELDS")
    _require(document["schema"] == FREEZE_SCHEMA
             and document["status"] == "RESEARCH_ONLY"
             and document["production_recommendations"] == "DISABLED",
             "UNSAFE_SEAL_STATUS")
    for key in SHA_FIELDS | frozenset(("seal_sha256_unanchored",)):
        _require(type(document[key]) is str and HASH.fullmatch(document[key]) is not None,
                 "INVALID_SEAL_DIGEST")
    _require(type(document["model_code_commit_claimed"]) is str
             and COMMIT.fullmatch(document["model_code_commit_claimed"]) is not None,
             "INVALID_MODEL_COMMIT_CLAIM")
    _require(type(document["forecast_raw_byte_count"]) is int
             and 1 <= document["forecast_raw_byte_count"] <= 64000,
             "INVALID_FORECAST_SIZE_CLAIM")
    for key in TRUE_FLAGS:
        _require(document[key] is True, "UNSAFE_SEAL_ASSERTIONS")
    for key in FALSE_FLAGS:
        _require(document[key] is False, "UNSAFE_SEAL_ASSERTIONS")
    for key in ZERO_FIELDS:
        _require(type(document[key]) is int and document[key] == 0,
                 "UNSAFE_SAMPLE_COUNT")
    payload = {k: v for k, v in document.items() if k != "seal_sha256_unanchored"}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False).encode("utf-8")
    _require(hmac.compare_digest(
        hashlib.sha256(canonical).hexdigest(), document["seal_sha256_unanchored"]),
        "LOCAL_SEAL_CHECKSUM_MISMATCH")
    trained, predicted, kickoff = (_timestamp(document[key]) for key in TIME_FIELDS)
    clock = datetime.now(timezone.utc) if now is None else now
    _require(type(clock) is datetime and clock.tzinfo is not None
             and clock.utcoffset() is not None, "INVALID_SIGNER_CLOCK")
    clock = clock.astimezone(timezone.utc)
    _require(trained <= predicted <= clock, "FUTURE_OR_LEAKY_PREDICTION_CLAIM")
    _require(predicted < kickoff - timedelta(minutes=10),
             "CLAIMED_PREDICTION_TOO_LATE")
    # Protect against delayed Actions queue/network: require a 20-minute
    # *initial* margin. Independent auditor will verify actual Rekor time.
    _require(clock < kickoff - timedelta(minutes=20),
             "SIGNER_STARTED_TOO_LATE")
    return safe_json_bytes


def decode_dispatch_seal(value, *, expected_sha256, now=None):
    _require(type(value) is str and 0 < len(value) <= MAX_BASE64_CHARS,
             "INVALID_DISPATCH_BASE64")
    try:
        data = base64.b64decode(value.encode("ascii"), validate=True)
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise IntakeError("INVALID_DISPATCH_BASE64") from exc
    return validate_sanitized_seal(data, expected_sha256=expected_sha256, now=now)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        data = decode_dispatch_seal(os.environ.get("SANITIZED_SEAL_BASE64", ""),
                                    expected_sha256=os.environ.get("EXPECTED_SEAL_SHA256", ""))
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(args.output, flags, 0o600), "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(data)  # Preserve EXACT signed subject bytes.
    except (IntakeError, OSError, ValueError) as exc:
        # Never echo input, file path, SHA fingerprint or private data.
        print(json.dumps({"status": "HOLD", "reason": str(exc) if isinstance(exc, IntakeError)
                          else "UNSAFE_SIGNER_OUTPUT", "production_recommendations": "DISABLED"}))
        return 1
    print(json.dumps({"status": "RESEARCH_ONLY", "safe_seal_written": True,
                      "real_source_authenticated": False,
                      "certified_forward_samples": 0,
                      "production_recommendations": "DISABLED"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
