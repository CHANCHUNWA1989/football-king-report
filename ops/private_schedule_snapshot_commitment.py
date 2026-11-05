"""Local two-source schedule commitments, NOT a trusted provenance anchor.

Only suitable for owner-only private offline audits. A SHA-256 commitment
detects local alteration against an already retained receipt; it does not
establish when either schedule was downloaded, identify real publishers or
create an independently authenticated actual kickoff. Never publish the
commitment or hashes without a separate privacy/licensing review: hashes of
small or identifiable data sets can be correlatable.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path

from private_kickoff_crosswalk_gate import CrosswalkError, crosscheck
from private_quote_forward_freeze import FreezeError, _json_bytes_object
from private_quote_snapshot_receipt import (
    ReceiptError, _payload_receipt, _read_raw_file, _write_private_new,
)

SCHEMA = "football-king-private-schedule-commitment-v1"
REPLAY_SCHEMA = "football-king-private-schedule-commitment-replay-v1"
MAX_SEAL_BYTES = 65_536
MAX_SCHEDULE_BYTES = 1_000_000
SHA_KEYS = (
    "local_source_descriptor_sha256_a",
    "local_source_descriptor_sha256_b",
    "forecast_seal_raw_bytes_sha256",
)
SAFE_FALSE = (
    "schedule_bytes_externally_attested",
    "publisher_identity_independently_authenticated",
    "publisher_independence_independently_authenticated",
    "claimed_capture_clock_independently_authenticated",
    "real_kickoff_independently_authenticated",
    "quoted_market_prices_independently_authenticated",
    "eligible_for_model_scoring",
    "eligible_for_betting_promotion",
)


class CommitmentError(ValueError):
    """Non-sensitive error code only."""


def _fail(code):
    raise CommitmentError(code)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _stable(data):
    return json.dumps(
        data, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _seal_from_raw(seal_raw):
    if type(seal_raw) is not bytes or not 0 < len(seal_raw) <= MAX_SEAL_BYTES:
        _fail("INVALID_FORECAST_SEAL_BYTES")
    try:
        return _json_bytes_object(seal_raw)
    except (FreezeError, ReceiptError, ValueError, TypeError, RecursionError) as exc:
        raise CommitmentError("INVALID_FORECAST_SEAL_JSON") from exc


def make_commitment(raw_odds, receipt, fixture, market,
                    forecast_raw, seal_raw, sources):
    """Enforce both actual bytes, exact crosswalk and deterministic private ID."""
    seal = _seal_from_raw(seal_raw)
    try:
        structural = crosscheck(raw_odds, receipt, fixture, market,
                                forecast_raw, seal, sources)
    except (CrosswalkError, FreezeError, ReceiptError, TypeError, ValueError,
            OverflowError, RecursionError) as exc:
        raise CommitmentError("CROSSWALK_OR_SEAL_REPLAY_REJECTED") from exc
    if (structural.get("status") != "RESEARCH_ONLY"
            or structural.get("production_recommendations") != "DISABLED"
            or structural.get("certified_independent_forward_samples") != 0
            or structural.get("actual_kickoff_independently_confirmed") is not False):
        _fail("UNSAFE_SCHEDULE_CROSSWALK_OUTPUT")
    if type(sources) not in (list, tuple) or len(sources) != 2:
        _fail("TWO_PRIVATE_SCHEDULES_REQUIRED")
    bindings = []
    for source in sources:
        if type(source) is not dict or set(source) != {
                "provider_namespace", "snapshot_bytes", "captured_utc",
                "source_event_id"}:
            _fail("INVALID_SOURCE_DESCRIPTOR")
        if type(source["snapshot_bytes"]) is not bytes:
            _fail("INVALID_SOURCE_SNAPSHOT")
        # Full native IDs, names, and capture claims are committed to locally
        # but NEVER included in the report in cleartext.
        descriptor = {
            "namespace": source["provider_namespace"],
            "source_event_id": source["source_event_id"],
            "claimed_capture_time": source["captured_utc"],
            "snapshot_sha256": _sha(source["snapshot_bytes"]),
            "snapshot_byte_length": len(source["snapshot_bytes"]),
        }
        bindings.append((source["provider_namespace"], _sha(_stable(descriptor))))
    bindings.sort(key=lambda pair: pair[0])
    if bindings[0][0] == bindings[1][0] or bindings[0][1] == bindings[1][1]:
        _fail("AMBIGUOUS_SCHEDULE_COMMITMENTS")
    manifest = {
        "schema": SCHEMA,
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "forecast_seal_raw_bytes_sha256": _sha(seal_raw),
        "local_source_descriptor_sha256_a": bindings[0][1],
        "local_source_descriptor_sha256_b": bindings[1][1],
        "sources_checked_as_local_claims": 2,
        "private_forecast_seal_and_schedule_structure_replayed": True,
        "schedule_bytes_externally_attested": False,
        "publisher_identity_independently_authenticated": False,
        "publisher_independence_independently_authenticated": False,
        "claimed_capture_clock_independently_authenticated": False,
        "real_kickoff_independently_authenticated": False,
        "quoted_market_prices_independently_authenticated": False,
        "eligible_for_model_scoring": False,
        "eligible_for_betting_promotion": False,
        "certified_independent_forward_samples": 0,
    }
    manifest["manifest_sha256_unanchored"] = _sha(_stable(manifest))
    return manifest


def replay_commitment(raw_odds, receipt, fixture, market,
                      forecast_raw, seal_raw, sources, saved):
    """Strict replay against saved private manifest, including all false flags."""
    if type(saved) is not dict or saved.get("schema") != SCHEMA:
        _fail("INVALID_SAVED_COMMITMENT")
    computed = make_commitment(raw_odds, receipt, fixture, market,
                               forecast_raw, seal_raw, sources)
    if (set(saved) != set(computed)
            or not hmac.compare_digest(_sha(_stable(saved)), _sha(_stable(computed)))):
        _fail("SCHEDULE_COMMITMENT_REPLAY_MISMATCH")
    return {
        "schema": REPLAY_SCHEMA,
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "local_schedule_manifest_bytes_and_semantics_replayed": True,
        "local_manifest_sha256_unanchored": computed["manifest_sha256_unanchored"],
        "schedule_bytes_externally_attested": False,
        "source_capture_clock_authenticated": False,
        "actual_kickoff_authenticated": False,
        "certified_independent_forward_samples": 0,
        "eligible_for_model_scoring": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("raw-odds", "receipt", "fixture", "market", "forecast", "seal",
                 "source-a", "source-b", "output"):
        parser.add_argument("--" + flag, type=Path, required=True)
    for flag in ("source-a-name", "source-a-id", "source-a-captured-utc",
                 "source-b-name", "source-b-id", "source-b-captured-utc"):
        parser.add_argument("--" + flag, required=True)
    parser.add_argument("--verify-commitment", type=Path)
    args = parser.parse_args(argv)
    try:
        odds = _read_raw_file(args.raw_odds)
        receipt = _payload_receipt(_read_raw_file(args.receipt))
        fixture = _json_bytes_object(_read_raw_file(args.fixture))
        market = _json_bytes_object(_read_raw_file(args.market))
        forecast = _read_raw_file(args.forecast)
        seal_raw = _read_raw_file(args.seal)
        sources = [
            {"provider_namespace": args.source_a_name, "source_event_id": args.source_a_id,
             "captured_utc": args.source_a_captured_utc,
             "snapshot_bytes": _read_raw_file(args.source_a)},
            {"provider_namespace": args.source_b_name, "source_event_id": args.source_b_id,
             "captured_utc": args.source_b_captured_utc,
             "snapshot_bytes": _read_raw_file(args.source_b)},
        ]
        if args.verify_commitment:
            saved = _json_bytes_object(_read_raw_file(args.verify_commitment))
            output = replay_commitment(odds, receipt, fixture, market,
                                       forecast, seal_raw, sources, saved)
        else:
            output = make_commitment(odds, receipt, fixture, market,
                                     forecast, seal_raw, sources)
        _write_private_new(args.output, output)
    except (CommitmentError, CrosswalkError, ReceiptError, FreezeError,
            OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "HOLD",
                          "reason": str(exc) if isinstance(exc, CommitmentError)
                          else "INVALID_PRIVATE_INPUT",
                          "production_recommendations": "DISABLED"}))
        return 1
    print(json.dumps({
        "status": "HOLD",
        "local_schedule_commitment_replayed":
            output.get("local_schedule_manifest_bytes_and_semantics_replayed") is True,
        "certified_independent_forward_samples": 0,
        "production_recommendations": "DISABLED",
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
