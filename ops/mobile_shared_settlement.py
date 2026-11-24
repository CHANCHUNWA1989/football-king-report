"""Single-source iPhone research report preflight; strict archive ref, no publish.

The only public entrypoint requires a REAL fixed official remote-ref check,
pinned compressed Git blobs, complete legacy evidence and parity of both
existing iPhone report builders. No action writes main, changes Pages or
enables betting. The pure _assemble function supports synthetic unit tests.
"""

import argparse
import hashlib
import json
from pathlib import Path

from ops.isolated_settlement_bridge import (
    _limited_bytes, _read_json, reconcile_official_remote,
)
from ops.mobile_settlement_parity_preflight import CutoverHold, preflight


def _hash_canonical(doc):
    """Deterministic byte fingerprint for the ONE common in-memory document."""
    return hashlib.sha256(json.dumps(
        doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False).encode("utf-8")).hexdigest()


def _assemble(legacy, candidate, bridge_receipt, gates, market, *, now=None):
    """Pure research dry-run. No caller may interpret this as release proof."""
    if not isinstance(bridge_receipt, dict):
        raise CutoverHold("MISSING_ARCHIVE_RECEIPT")
    if bridge_receipt.get("production_recommendations") != "DISABLED":
        raise CutoverHold("UNSAFE_ARCHIVE_RECEIPT")
    parity = preflight(legacy, candidate, gates, market, now=now)
    if not parity["candidate_same_input_count_parity"]:
        raise CutoverHold("CANDIDATE_REPORT_SOURCE_SPLIT")
    if parity["candidate_sample_count"] != bridge_receipt.get("combined_samples"):
        raise CutoverHold("ARCHIVE_RECEIPT_SAMPLE_COUNT_MISMATCH")
    if parity["legacy_sample_count"] != bridge_receipt.get("legacy_samples"):
        raise CutoverHold("LEGACY_RECEIPT_SAMPLE_COUNT_MISMATCH")
    return {
        "schema": "football-king-single-source-mobile-cutover-preview-v1",
        "status": "HOLD_RESEARCH_SHARED_INPUT_PREVIEW_ONLY",
        "canonical_settlement_sha256": _hash_canonical(candidate),
        "archive_head_sha": bridge_receipt["archive_head_sha"],
        "legacy_sha256": bridge_receipt["legacy_sha256"],
        "archive_batches": bridge_receipt["archive_batches"],
        "legacy_samples": parity["legacy_sample_count"],
        "candidate_samples": parity["candidate_sample_count"],
        "daily_scorecard_samples": parity["candidate_daily_scorecard_count"],
        "official_readiness_samples": parity["candidate_public_readiness_count_if_switched"],
        "current_workflow_source_split_detected": not parity["current_workflow_count_parity"],
        "candidate_same_input_count_parity": True,
        "archive_ref_checked": bool(bridge_receipt.get("remote_ref_checked")),
        "archive_ref_independently_attested": False,
        "verified_final_scores": False,
        "site_published": False,
        "main_modified": False,
        "source_switch_authorized": False,
        "production_recommendations": "DISABLED",
    }


def preview_from_official_archive(legacy_path, archive_checkout, expected_archive_sha,
                                  gates_path, market_path, *, now=None):
    """Full gate. Never accept a caller-selected alternative verifier or ref."""
    # The strict bridge verifies official git origin/ref BEFORE and AFTER
    # reading, HEAD SHA, and every compressed batch's pinned Git tree blob.
    candidate, receipt = reconcile_official_remote(
        legacy_path, archive_checkout, expected_archive_sha)
    if not (receipt.get("remote_ref_checked") is True
            and receipt.get("remote_ref_stable_during_read") is True
            and receipt.get("archive_head_sha") == expected_archive_sha):
        raise CutoverHold("OFFICIAL_ARCHIVE_READ_NOT_CONFIRMED")
    legacy_bytes = _limited_bytes(Path(legacy_path))
    # Guard against a legacy-file swap between strict reconciliation and
    # both report builders; the original archive receipt binds these bytes.
    if hashlib.sha256(legacy_bytes).hexdigest() != receipt.get("legacy_sha256"):
        raise CutoverHold("LEGACY_SOURCE_CHANGED_DURING_PREVIEW")
    legacy = _read_json(legacy_bytes)
    gates = _read_json(_limited_bytes(Path(gates_path)))
    market = _read_json(_limited_bytes(Path(market_path)))
    return _assemble(legacy, candidate, receipt, gates, market, now=now)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy", type=Path, required=True)
    parser.add_argument("--archive-checkout", type=Path, required=True)
    parser.add_argument("--expected-archive-sha", required=True)
    parser.add_argument("--gates", type=Path, required=True)
    parser.add_argument("--market", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = preview_from_official_archive(
            args.legacy, args.archive_checkout, args.expected_archive_sha,
            args.gates, args.market)
    except (ValueError, OSError, TypeError, KeyError, RuntimeError):
        print(json.dumps({"status": "HOLD_OFFICIAL_SHARED_SNAPSHOT_NOT_VERIFIED",
                          "source_switch_authorized": False,
                          "production_recommendations": "DISABLED"}))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
