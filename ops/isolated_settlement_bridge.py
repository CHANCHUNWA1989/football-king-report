"""Offline-only read compatibility bridge for legacy + isolated settlement batches.

The caller MUST pin a checked-out archive branch HEAD to a trusted SHA.
No remote API, no git write, no workflow modification and no model promotion.
Legacy evidence is always mandatory and remains unchanged.
"""

import argparse
from datetime import date
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess

from evidence_merge import merge, validate

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
BATCH = re.compile(
    r"settlement_batches/([0-9]{4})/([0-9]{2})/([0-9]{2})/"
    r"([1-9][0-9]{0,19})-([1-9][0-9]{0,19})\.json\.gz\Z")
MAX_BYTES = 8_000_000
MAX_BATCHES = 256
MAX_TOTAL_BYTES = 32_000_000


class BridgeHold(ValueError):
    """A bounded, public-safe rejection that never reveals original payloads."""


def _no_duplicate_keys(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise BridgeHold("DUPLICATE_JSON_KEY")
        out[key] = value
    return out


def _reject_nonfinite(_):
    raise BridgeHold("NONFINITE_JSON_NUMBER")


def _read_json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_no_duplicate_keys,
                          parse_constant=_reject_nonfinite)
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        if isinstance(exc, BridgeHold):
            raise
        raise BridgeHold("INVALID_SETTLEMENT_JSON") from exc


def _limited_bytes(path, *, compressed=False):
    if path.is_symlink() or not path.is_file():
        raise BridgeHold("UNSAFE_OR_MISSING_SETTLEMENT_FILE")
    if not 0 < path.stat().st_size <= MAX_BYTES:
        raise BridgeHold("SETTLEMENT_INPUT_SIZE_LIMIT")
    try:
        if compressed:
            with gzip.open(path, "rb") as stream:
                content = stream.read(MAX_BYTES + 1)
        else:
            with path.open("rb") as stream:
                content = stream.read(MAX_BYTES + 1)
    except (OSError, EOFError) as exc:
        raise BridgeHold("INVALID_SETTLEMENT_COMPRESSION") from exc
    if not 0 < len(content) <= MAX_BYTES:
        raise BridgeHold("SETTLEMENT_DECOMPRESSED_SIZE_LIMIT")
    return content


def _archive_paths(root):
    base = root / "settlement_batches"
    if base.is_symlink() or not base.is_dir():
        raise BridgeHold("MISSING_ISOLATED_SETTLEMENT_ARCHIVE")
    files = []
    for entry in base.rglob("*"):
        if entry.is_symlink():
            raise BridgeHold("SYMLINK_IN_SETTLEMENT_ARCHIVE")
        if entry.is_dir():
            continue
        rel = entry.relative_to(root).as_posix()
        match = BATCH.fullmatch(rel)
        if not entry.is_file() or match is None:
            raise BridgeHold("UNEXPECTED_SETTLEMENT_ARCHIVE_PATH")
        try:
            date(int(match[1]), int(match[2]), int(match[3]))
        except ValueError as exc:
            raise BridgeHold("INVALID_SETTLEMENT_ARCHIVE_DAY") from exc
        files.append(entry)
        if len(files) > MAX_BATCHES:
            raise BridgeHold("SETTLEMENT_BATCH_LIMIT")
    if not files:
        raise BridgeHold("NO_ISOLATED_SETTLEMENT_BATCHES")
    return sorted(files)


def _verified_checkout(root, expected_sha):
    if not isinstance(expected_sha, str) or not SHA40.fullmatch(expected_sha):
        raise BridgeHold("INVALID_ARCHIVE_HEAD_SHA")
    if root.is_symlink() or not root.is_dir():
        raise BridgeHold("INVALID_ARCHIVE_CHECKOUT")
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
            capture_output=True, check=False, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        raise BridgeHold("ARCHIVE_HEAD_CHECK_UNAVAILABLE") from exc
    if proc.returncode or proc.stdout.strip() != expected_sha:
        raise BridgeHold("ARCHIVE_HEAD_SHA_MISMATCH")


def reconcile(legacy_path, archive_checkout, expected_archive_sha):
    """Return (compatible cumulative document, provenance receipt), never write."""
    legacy_path = Path(legacy_path)
    archive_checkout = Path(archive_checkout)
    if legacy_path.is_symlink():
        raise BridgeHold("UNSAFE_OR_MISSING_SETTLEMENT_FILE")
    _verified_checkout(archive_checkout, expected_archive_sha)
    original = _limited_bytes(legacy_path)
    old = _read_json(original)
    validate(old)  # Must not silently drop the historic main state.
    old_n = len(old["samples"])
    combined = old
    total_decoded = len(original)
    batch_files = _archive_paths(archive_checkout)
    for item in batch_files:
        raw = _limited_bytes(item, compressed=True)
        total_decoded += len(raw)
        if total_decoded > MAX_TOTAL_BYTES:
            raise BridgeHold("SETTLEMENT_TOTAL_SIZE_LIMIT")
        incoming = _read_json(raw)
        validate(incoming)
        combined = merge(combined, incoming)  # rejects changed same-key outcome
    new_n = len(combined["samples"]) - old_n
    if new_n < 0 or combined["production_recommendations"] != "DISABLED":
        raise BridgeHold("UNSAFE_SETTLEMENT_COMPATIBILITY_RESULT")
    # Do not promote results merely because the merge was structurally valid.
    combined["newly_settled"] = new_n
    receipt = {
        "status": "READ_COMPATIBLE_RESEARCH_ONLY_NOT_RELEASE",
        "legacy_samples": old_n,
        "archive_batches": len(batch_files),
        "new_samples": new_n,
        "combined_samples": len(combined["samples"]),
        "legacy_sha256": hashlib.sha256(original).hexdigest(),
        "archive_head_sha": expected_archive_sha,
        "results_independently_verified": False,
        "profitability_verified": False,
        "production_recommendations": "DISABLED",
    }
    return combined, receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy", type=Path, required=True)
    parser.add_argument("--archive-checkout", type=Path, required=True)
    parser.add_argument("--expected-archive-sha", required=True)
    # No output-to-source file: stdout is a bounded receipt only. Consumers
    # must explicitly integrate this library after independent approval.
    args = parser.parse_args(argv)
    try:
        _, receipt = reconcile(args.legacy, args.archive_checkout,
                               args.expected_archive_sha)
    except (BridgeHold, ValueError, OSError):
        print(json.dumps({"status": "HOLD_SETTLEMENT_COMPATIBILITY_NOT_CONFIRMED",
                          "production_recommendations": "DISABLED"}))
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
