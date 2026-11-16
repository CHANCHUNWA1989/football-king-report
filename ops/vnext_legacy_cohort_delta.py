"""Read-only cohort drift guard between TWO pinned Git archive snapshots.

Separate from source authentication and PR #451 model scoring. Compares
*every* field of each older record, not just outcome y or p/m vectors.
A clean append-only result is NOT licensed source evidence, a real forecast
witness, publisher attestation, result truth, OOS certification or positive EV.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

from ops.vnext_legacy_settled_readiness import (
    MAX_ARCHIVE_BYTES,
    _reject_nonfinite,
    _uniquely_named_object,
    audit_archive_bytes,
)

SCHEMA = "football-king-vnext-legacy-cohort-delta-v1"


def _records(raw):
    archive = json.loads(raw, object_pairs_hook=_uniquely_named_object,
                         parse_constant=_reject_nonfinite)
    return archive["samples"]


def _canonical_digest(row):
    # Enforce exact JSON value types, complete field coverage and stable
    # dictionary-key order without trusting the input's whitespace.
    encoded = json.dumps(row, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return sha256(encoded).hexdigest()


def audit_cohort_delta(older_bytes, newer_bytes, *,
                       expected_old_git_blob_sha1, expected_new_git_blob_sha1):
    """Compare two independently Git-blob-pinned archives, remain HOLD.

    Independent reference here means SHA pins must come from a trusted
    GitHub commit fetched out of band. The function cannot establish that
    those references are independently signed or that scores are real.
    """
    if expected_old_git_blob_sha1 == expected_new_git_blob_sha1:
        raise ValueError("IDENTICAL_ARCHIVE_REFERENCES")
    old_review = audit_archive_bytes(
        older_bytes, expected_git_blob_sha1=expected_old_git_blob_sha1)
    new_review = audit_archive_bytes(
        newer_bytes, expected_git_blob_sha1=expected_new_git_blob_sha1)
    old_rows = _records(older_bytes)
    new_rows = _records(newer_bytes)
    old_order = [item["key"] for item in old_rows]
    new_order = [item["key"] for item in new_rows]
    old_digest = {item["key"]: _canonical_digest(item) for item in old_rows}
    new_digest = {item["key"]: _canonical_digest(item) for item in new_rows}
    before = set(old_digest)
    after = set(new_digest)
    overlap = before & after
    modified = sum(old_digest[key] != new_digest[key] for key in overlap)
    removed = len(before - after)
    added = len(after - before)
    unchanged = len(overlap) - modified
    preserved_prefix = (len(new_order) >= len(old_order)
                        and new_order[:len(old_order)] == old_order)
    append_only = (len(new_rows) > len(old_rows) and preserved_prefix
                   and modified == 0 and removed == 0
                   and added == len(new_rows) - len(old_rows))
    return {
        "schema": SCHEMA,
        "status": "HOLD",
        "cohort_integrity": (
            "APPEND_ONLY_BYTES_CONSISTENT_RESEARCH"
            if append_only else "HOLD_HISTORICAL_RECORD_DRIFT"
        ),
        "append_only_verified_between_pinned_archives": append_only,
        "older_archive_git_blob_sha1": expected_old_git_blob_sha1,
        "newer_archive_git_blob_sha1": expected_new_git_blob_sha1,
        "older_rows": len(old_rows),
        "newer_rows": len(new_rows),
        "overlapping_rows": len(overlap),
        "unchanged_overlap_rows": unchanged,
        "modified_overlap_rows": modified,
        "removed_rows": removed,
        "newly_appended_rows": added,
        "older_rows_preserved_as_prefix": preserved_prefix,
        "newer_unsupported_certification_claim_rows": (
            new_review["unsupported_certification_claim_rows"]
        ),
        "older_unsupported_certification_claim_rows": (
            old_review["unsupported_certification_claim_rows"]
        ),
        "archive_bytes_match_externally_supplied_git_refs": True,
        "original_publisher_identity_independently_verified": False,
        "external_witness_independently_verified": False,
        "independent_result_truth_verified": False,
        "commercial_data_rights_verified": False,
        "certified_prospective_rows": 0,
        "positive_ev_verified": False,
        "profitability_verified": False,
        "model_promoted": False,
        "production_recommendations": "DISABLED",
        "note": (
            "Relative content integrity only. Git blob IDs do not prove "
            "authentic bookmaker prices, provider source identity, legal use, "
            "pre-match capture, real result truth or any betting edge."
        ),
    }


def _load_local_archive(path):
    file = Path(path)
    if file.is_symlink() or not file.is_file():
        raise ValueError("UNSAFE_ARCHIVE_PATH")
    if not 0 < file.stat().st_size <= MAX_ARCHIVE_BYTES:
        raise ValueError("MISSING_OR_OVERSIZED_ARCHIVE_BYTES")
    return file.read_bytes()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fail closed on old-vs-new archive cohort drift")
    parser.add_argument("--older", required=True)
    parser.add_argument("--newer", required=True)
    parser.add_argument("--expected-old-git-blob-sha1", required=True)
    parser.add_argument("--expected-new-git-blob-sha1", required=True)
    args = parser.parse_args(argv)
    try:
        report = audit_cohort_delta(
            _load_local_archive(args.older), _load_local_archive(args.newer),
            expected_old_git_blob_sha1=args.expected_old_git_blob_sha1,
            expected_new_git_blob_sha1=args.expected_new_git_blob_sha1,
        )
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "HOLD",
                          "production_recommendations": "DISABLED",
                          "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0 if report["append_only_verified_between_pinned_archives"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
