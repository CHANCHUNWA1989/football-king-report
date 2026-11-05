"""Offline prospective scoreline freeze tied to ONE replayed private quote line.

A local SHA chain is NOT a historical witness: all timestamps and model fields
are self-reported. Without an independently verified pre-kickoff signature/time
anchor this cannot count toward certified forward samples or promote picks.
No remote calls, real money actions, or raw private prices are made/exported.
"""
import argparse
from datetime import timedelta
import hashlib
import hmac
import json
from math import isfinite
from pathlib import Path
import re

from private_quote_fixture_binding import (
    BindingError, _instant, _validate_inputs, bind_private_fixture,
)
from private_quote_snapshot_receipt import (
    ReceiptError, _pairs_unique, _nonfinite, _read_raw_file,
    _payload_receipt, _write_private_new,
)

SCHEMA = "football-king-private-prospective-freeze-v1"
FORECAST_SCHEMA = "football-king-private-scoreline-forecast-v1"
FORECAST_FIELDS = frozenset((
    "schema", "provider_event_id", "market_type", "market_line_quarter_units",
    "model_version", "model_code_commit", "training_cutoff_utc",
    "prediction_utc", "raw_snapshot_sha256", "quote_receipt_sha256_unanchored",
    "score_distribution", "production_recommendations",
))
MAX_FORECAST_BYTES = 64_000
MAX_SCORE_GOALS = 12
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class FreezeError(ValueError):
    """Fixed non-sensitive error code."""


def _fail(reason):
    raise FreezeError(reason)


def _hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _json_bytes(raw):
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_FORECAST_BYTES:
        _fail("INVALID_FORECAST_BYTES")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs_unique,
                           parse_constant=_nonfinite)
    except (ValueError, TypeError, UnicodeDecodeError, RecursionError) as exc:
        raise FreezeError("INVALID_FORECAST_JSON") from exc
    if type(value) is not dict or set(value) != FORECAST_FIELDS:
        _fail("INVALID_FORECAST_SCHEMA")
    return value


def _validate_probability_grid(value):
    if type(value) is not list or not 1 <= len(value) <= (MAX_SCORE_GOALS + 1) ** 2:
        _fail("INVALID_SCORE_DISTRIBUTION")
    seen = set()
    total = 0.0
    for row in value:
        if (type(row) is not list or len(row) != 3
                or type(row[0]) is not int or not 0 <= row[0] <= MAX_SCORE_GOALS
                or type(row[1]) is not int or not 0 <= row[1] <= MAX_SCORE_GOALS
                or type(row[2]) not in (int, float)
                or not isfinite(row[2]) or not 0 <= row[2] <= 1):
            _fail("INVALID_SCORE_DISTRIBUTION")
        key = (row[0], row[1])
        if key in seen:
            _fail("DUPLICATE_SCORELINE")
        seen.add(key)
        total += row[2]
    if abs(total - 1.0) > 0.000001:
        _fail("UNNORMALIZED_SCORE_DISTRIBUTION")


def freeze(raw_snapshot, receipt, fixture, market, forecast_raw):
    """Recompute market receipt+line binding and freeze model bytes as one claim."""
    kickoff, market_type, line_units = _validate_inputs(fixture, market)
    if type(receipt) is not dict:
        _fail("INVALID_QUOTE_RECEIPT")
    try:
        binding = bind_private_fixture(raw_snapshot, receipt, fixture, market)
    except (ReceiptError, BindingError, KeyError, TypeError, ValueError) as exc:
        raise FreezeError("UNVERIFIED_QUOTE_FIXTURE_BINDING") from exc
    if (binding.get("status") != "RESEARCH_ONLY"
            or binding.get("requested_line_structurally_observed") is not True
            or type(binding.get("atomic_bookmaker_groups_for_requested_line")) is not int
            or binding["atomic_bookmaker_groups_for_requested_line"] < 1):
        _fail("NO_ATOMIC_PREMATCH_MARKET_LINE")
    forecast = _json_bytes(forecast_raw)
    if (forecast["schema"] != FORECAST_SCHEMA
            or forecast["production_recommendations"] != "DISABLED"
            or forecast["provider_event_id"] != fixture["provider_event_id"]
            or forecast["market_type"] != market_type
            or type(forecast["market_line_quarter_units"]) is not
            (type(None) if market_type == "h2h" else int)
            or forecast["market_line_quarter_units"] != line_units):
        _fail("FORECAST_FIXTURE_OR_MARKET_MISMATCH")
    model_version = forecast["model_version"]
    if (type(model_version) is not str or not 1 <= len(model_version) <= 80
            or not model_version.isprintable()
            or type(forecast["model_code_commit"]) is not str
            or not GIT_COMMIT.fullmatch(forecast["model_code_commit"])):
        _fail("INVALID_MODEL_VERSION")
    sha = forecast["raw_snapshot_sha256"]
    receipt_sha = forecast["quote_receipt_sha256_unanchored"]
    if (type(sha) is not str or not SHA256.fullmatch(sha)
            or type(receipt_sha) is not str or not SHA256.fullmatch(receipt_sha)
            or not hmac.compare_digest(sha, receipt.get("raw_response_sha256", ""))
            or not hmac.compare_digest(
                receipt_sha, receipt.get("receipt_sha256_unanchored", ""))):
        _fail("FORECAST_QUOTE_DIGEST_MISMATCH")
    try:
        captured = _instant(receipt["captured_utc_claimed_by_caller"])
        predicted = _instant(forecast["prediction_utc"])
        train_cutoff = _instant(forecast["training_cutoff_utc"])
    except (BindingError, KeyError) as exc:
        raise FreezeError("INVALID_FORECAST_TIME") from exc
    if not train_cutoff <= predicted or not captured <= predicted < kickoff - timedelta(minutes=10):
        _fail("NON_PROSPECTIVE_FORECAST_CLOCK")
    _validate_probability_grid(forecast["score_distribution"])
    # Hash the caller fixture+line privately; no event IDs or score distribution
    # are ever copied into a public report. This hash is not a crosswalk proof.
    binding_bytes = json.dumps({"fixture": fixture, "market": market},
                               sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                               allow_nan=False).encode("utf-8")
    sealed = {
        "schema": SCHEMA,
        "status": "RESEARCH_ONLY",
        "raw_snapshot_sha256": sha,
        "quote_receipt_sha256_unanchored": receipt_sha,
        "fixture_market_binding_sha256_unanchored": _hash_bytes(binding_bytes),
        "forecast_raw_bytes_sha256": _hash_bytes(forecast_raw),
        "forecast_raw_byte_count": len(forecast_raw),
        "model_code_commit_claimed": forecast["model_code_commit"],
        "training_cutoff_utc_claimed": train_cutoff.isoformat(),
        "prediction_utc_claimed": predicted.isoformat(),
        "kickoff_utc_claimed": kickoff.isoformat(),
        "raw_snapshot_binding_replayed": True,
        "exact_fixture_and_line_structurally_matched": True,
        "score_distribution_structurally_normalized": True,
        "training_data_leakage_independently_audited": False,
        "forecast_was_witnessed_before_kickoff": False,
        "fixture_source_independently_authenticated": False,
        "bookmaker_quote_independently_authenticated": False,
        "score_distribution_calibration_verified": False,
        "eligible_independently_verified_forward_samples": 0,
        "eligible_for_model_scoring": False,
        "executable_quote_verified": False,
        "model_edge_verified": False,
        "can_publish_pick": False,
        "production_recommendations": "DISABLED",
    }
    canonical = json.dumps(sealed, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"), allow_nan=False).encode("utf-8")
    sealed["seal_sha256_unanchored"] = _hash_bytes(canonical)
    return sealed


def verify_freeze(raw_snapshot, receipt, fixture, market, forecast_raw, seal):
    """Rebuild exact local integrity chain; NOT an independent time witness."""
    if type(seal) is not dict or seal.get("schema") != SCHEMA:
        _fail("INVALID_SEAL")
    if (type(seal.get("forecast_raw_bytes_sha256")) is not str
            or not SHA256.fullmatch(seal["forecast_raw_bytes_sha256"])
            or not hmac.compare_digest(
                _hash_bytes(forecast_raw) if type(forecast_raw) is bytes else "",
                seal["forecast_raw_bytes_sha256"])):
        _fail("FORECAST_BYTES_CHANGED")
    rebuilt = freeze(raw_snapshot, receipt, fixture, market, forecast_raw)
    if set(seal) != set(rebuilt) or seal != rebuilt:
        _fail("SEAL_REPLAY_MISMATCH")
    return {"schema": "football-king-private-prospective-seal-replay-v1",
            "local_bytes_and_semantics_replayed": True,
            "independently_witnessed_before_kickoff": False,
            "independent_forward_samples_credited": 0,
            "eligible_for_model_promotion": False,
            "status": "HOLD", "production_recommendations": "DISABLED"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-odds", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--market", type=Path, required=True)
    parser.add_argument("--forecast", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-seal", type=Path)
    args = parser.parse_args(argv)
    try:
        raw = _read_raw_file(args.raw_odds)
        receipt = _payload_receipt(_read_raw_file(args.receipt))
        fixture = _json_bytes_object(_read_raw_file(args.fixture))
        market = _json_bytes_object(_read_raw_file(args.market))
        forecast = _read_raw_file(args.forecast)
        if args.verify_seal is None:
            result = freeze(raw, receipt, fixture, market, forecast)
        else:
            seal = _json_bytes_object(_read_raw_file(args.verify_seal))
            result = verify_freeze(raw, receipt, fixture, market, forecast, seal)
        _write_private_new(args.output, result)
    except (ReceiptError, BindingError, FreezeError, OSError,
            ValueError, TypeError, OverflowError) as exc:
        reason = str(exc) if isinstance(exc, FreezeError) else "UNSAFE_OR_INVALID_PRIVATE_INPUT"
        print(json.dumps({"status": "HOLD", "reason": reason,
                          "production_recommendations": "DISABLED"}))
        return 1
    print(json.dumps({"status": result["status"],
                      "local_prospective_record_created": True,
                      "independently_witnessed_before_kickoff": False,
                      "production_recommendations": "DISABLED"}))
    return 0


def _json_bytes_object(raw):
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_FORECAST_BYTES:
        _fail("INVALID_PRIVATE_JSON_SIZE")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs_unique,
                           parse_constant=_nonfinite)
    except (ValueError, UnicodeDecodeError, TypeError, RecursionError) as exc:
        raise FreezeError("INVALID_PRIVATE_JSON") from exc
    if type(value) is not dict:
        _fail("INVALID_PRIVATE_JSON")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
