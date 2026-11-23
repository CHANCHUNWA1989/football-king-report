"""Opt-in isolated settlement writer; never writes to main or deploys itself.

The archive ref must already exist, and the caller must supply the current
legacy main evidence document. This is research preservation, not source
authentication or an independently reviewed production migration.
"""

import argparse
from datetime import date
import gzip
import json
from pathlib import Path
import re
import tempfile
import time

from ops.evidence_merge import merge, validate
from ops.archive_remote_ref_gate import verify_archive_writer_origin
from ops.archive_hosted_write_lock import require_independent_hosted_archive_custody
from ops.isolated_provenance_archive import (
    ARCHIVE_BRANCH, ARCHIVE_REF, TRACKING_REF, ArchiveGateError,
    _git, _remote_head,
)
from ops.isolated_settlement_bridge import (
    MAX_BYTES, _archive_paths, _limited_bytes, _read_json, reconcile,
)

RUN = re.compile(r"[1-9][0-9]{0,19}\Z")
DAY = re.compile(r"([0-9]{4})/([0-9]{2})/([0-9]{2})\Z")


def _safe_input(source, legacy):
    """Check both complete documents BEFORE any Git write."""
    source_raw = _limited_bytes(Path(source))
    legacy_raw = _limited_bytes(Path(legacy))
    incoming = _read_json(source_raw)
    old = _read_json(legacy_raw)
    validate(incoming)
    validate(old)
    merge(old, incoming)  # A changed historical fixture must fail closed.
    return source_raw, incoming


def _target(worktree, day, run_id, attempt):
    if not RUN.fullmatch(str(run_id)) or not RUN.fullmatch(str(attempt)):
        raise ArchiveGateError("INVALID_SETTLEMENT_RUN")
    match = DAY.fullmatch(str(day))
    if not match:
        raise ArchiveGateError("INVALID_SETTLEMENT_DAY")
    try:
        date(*(int(part) for part in match.groups()))
    except ValueError as exc:
        raise ArchiveGateError("INVALID_SETTLEMENT_DAY") from exc
    relative = Path("settlement_batches") / day / (str(run_id) + "-" + str(attempt) + ".json.gz")
    target = Path(worktree) / relative
    cursor = Path(worktree)
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink() or (cursor.exists() and
                                  not (cursor.is_dir() if cursor != target else cursor.is_file())):
            raise ArchiveGateError("UNSAFE_SETTLEMENT_TARGET")
    return target, relative


def append(source, legacy, repo, run_id, attempt, day, *, max_tries=3, retry_sleep=0):
    """Append exact incoming raw bytes as bounded gzip, with race-safe non-force push.

    Validate any archived cumulative evidence against mandatory legacy history,
    so one archive batch cannot silently contradict an earlier one.
    """
    source, legacy, repo = Path(source), Path(legacy), Path(repo)
    if max_tries not in (1, 2, 3) or repo.is_symlink() or not repo.is_dir():
        raise ArchiveGateError("INVALID_SETTLEMENT_WRITER_CONFIGURATION")
    # Fail fast on malformed fixture keys, unsafe production flags and
    # changed outcomes without touching a remote Git ref.
    raw, incoming = _safe_input(source, legacy)
    _target(repo, day, run_id, attempt)  # Validation only, no directory mutation.
    for cycle in range(max_tries):
        try:
            remote_sha = _remote_head(repo)
            _git(repo, "fetch", "--no-tags", "origin",
                 "+" + ARCHIVE_REF + ":" + TRACKING_REF)
            if _git(repo, "rev-parse", TRACKING_REF) != remote_sha:
                raise ArchiveGateError("CONCURRENT_ARCHIVE_REF_CHANGED")
            with tempfile.TemporaryDirectory(prefix="fk-settlement-worktree-") as temp:
                checkout = Path(temp) / "checkout"
                _git(repo, "worktree", "add", "--detach", str(checkout), remote_sha)
                try:
                    target, relative = _target(checkout, day, run_id, attempt)
                    # This branch can also contain the other independent
                    # forecast-provenance folder. Check all *settlement*
                    # batches, not unrelated existing files.
                    if (checkout / "settlement_batches").exists():
                        cumulative, _ = reconcile(legacy, checkout, remote_sha)
                    else:
                        cumulative = _read_json(_limited_bytes(legacy))
                        validate(cumulative)
                    merge(cumulative, incoming)  # No cross-batch outcome rewrites.
                    if target.exists():
                        previous = _limited_bytes(target, compressed=True)
                        if previous != raw:
                            raise ArchiveGateError("IMMUTABLE_SETTLEMENT_BATCH_COLLISION")
                        return {
                            "status": "ALREADY_ARCHIVED",
                            "branch": ARCHIVE_BRANCH, "new_files": 0,
                            "production_recommendations": "DISABLED",
                        }
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(gzip.compress(raw, mtime=0))
                    _git(checkout, "add", "--", relative.as_posix())
                    _git(checkout,
                         "-c", "user.name=football-king-archive-pilot",
                         "-c", "user.email=archive-pilot@users.noreply.github.com",
                         "commit", "-m", "Append immutable research settlement batch")
                    _git(checkout, "push", "origin", "HEAD:" + ARCHIVE_REF)
                    return {
                        "status": "SETTLEMENT_ARCHIVED_RESEARCH_ONLY",
                        "branch": ARCHIVE_BRANCH, "new_files": 1,
                        "production_recommendations": "DISABLED",
                    }
                finally:
                    _git(repo, "worktree", "remove", "--force", str(checkout))
        except ArchiveGateError as exc:
            # Hard failures must not be transformed into a "successful" retry.
            if str(exc) in {
                "ARCHIVE_BRANCH_NOT_PROVISIONED", "UNTRUSTED_ARCHIVE_REF",
                "IMMUTABLE_SETTLEMENT_BATCH_COLLISION",
                "UNSAFE_SETTLEMENT_TARGET",
            }:
                raise
            if cycle == max_tries - 1:
                raise ArchiveGateError("ISOLATED_SETTLEMENT_WRITE_NOT_CONFIRMED") from exc
            if retry_sleep:
                time.sleep(retry_sleep)
    raise ArchiveGateError("ISOLATED_SETTLEMENT_WRITE_NOT_CONFIRMED")


def append_official(source, legacy, repo, run_id, attempt, day,
                    *, max_tries=3, retry_sleep=0):
    """Future authorized archive writer path, refusing origin/push redirection.

    The legacy append entrypoint exists strictly for local synthetic fixture
    tests; the CLI uses this gated path, not the local-only function.
    """
    verify_archive_writer_origin(repo)
    # Block all hosted writes until a separately reviewed custody policy exists.
    require_independent_hosted_archive_custody()
    result = append(source, legacy, repo, run_id, attempt, day,
                    max_tries=max_tries, retry_sleep=retry_sleep)
    verify_archive_writer_origin(repo)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--legacy", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--day", required=True)
    args = parser.parse_args(argv)
    try:
        receipt = append_official(args.source, args.legacy, args.repo, args.run_id,
                                  args.attempt, args.day)
    except (ArchiveGateError, ValueError, OSError, RuntimeError):
        print(json.dumps({
            "status": "HOLD_SETTLEMENT_ARCHIVE_NOT_CONFIRMED",
            "production_recommendations": "DISABLED",
        }))
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
