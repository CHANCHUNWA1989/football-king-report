"""Opt-in research pilot: append-only forecast provenance to an existing Git ref.

No remote branch creation, no main write, no force-push and no authentication
setup. The calling workflow must provision the separate archive branch, audit
its readers, and obtain independent review before invoking this script.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from ops.archive_forecast_provenance import prepare
from ops.archive_remote_ref_gate import sanitized_git_env, verify_archive_writer_origin
from ops.archive_hosted_write_lock import require_independent_hosted_archive_custody

ARCHIVE_BRANCH = "research/forward-provenance-archive"
ARCHIVE_REF = "refs/heads/" + ARCHIVE_BRANCH
TRACKING_REF = "refs/remotes/origin/" + ARCHIVE_BRANCH
SHA = re.compile(r"[0-9a-f]{40}\Z")


class ArchiveGateError(ValueError):
    """Predictable fail-closed archive rejection (never include credentials)."""


def _git(cwd, *argv):
    proc = subprocess.run(["git", "-C", str(cwd), *argv], stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, text=True, check=False,
                          timeout=40, env=sanitized_git_env())
    if proc.returncode:
        raise ArchiveGateError("ARCHIVE_GIT_OPERATION_FAILED")
    return proc.stdout.strip()


def _remote_head(repo):
    # Must already exist. Never auto-create or redirect the archive to main.
    output = _git(repo, "ls-remote", "--heads", "origin", ARCHIVE_REF)
    line = output.splitlines()
    if len(line) != 1:
        raise ArchiveGateError("ARCHIVE_BRANCH_NOT_PROVISIONED")
    fields = line[0].split()
    if len(fields) != 2 or not SHA.fullmatch(fields[0]) or fields[1] != ARCHIVE_REF:
        raise ArchiveGateError("UNTRUSTED_ARCHIVE_REF")
    return fields[0]


def append(proof, repo, run_id, attempt, day, *, max_tries=3, retry_sleep=0):
    """Add a complete 10-file batch to a fixed non-main ref, or fail closed."""
    repo = Path(repo)
    proof = Path(proof)
    if max_tries not in (1, 2, 3):
        raise ArchiveGateError("INVALID_RETRY_POLICY")
    if not repo.is_dir() or repo.is_symlink():
        raise ArchiveGateError("INVALID_WORKTREE")
    # Inspect the exact remote branch, not a locally cached potentially stale ref.
    for attempt_no in range(max_tries):
        try:
            before = _remote_head(repo)
            _git(repo, "fetch", "--no-tags", "origin", "+" + ARCHIVE_REF + ":" + TRACKING_REF)
            fetched = _git(repo, "rev-parse", TRACKING_REF)
            if fetched != before:
                raise ArchiveGateError("CONCURRENT_ARCHIVE_REF_CHANGED")
            with tempfile.TemporaryDirectory(prefix="fk-provenance-worktree-") as tmp:
                worktree = Path(tmp) / "checkout"
                _git(repo, "worktree", "add", "--detach", str(worktree), before)
                try:
                    created = prepare(proof, worktree, run_id, attempt, day=day)
                    if not created:
                        return {"status": "ALREADY_ARCHIVED", "branch": ARCHIVE_BRANCH,
                                "new_files": 0, "production_recommendations": "DISABLED"}
                    if len(created) != 10 or any(
                            not p.startswith("forecast_provenance/") for p in created):
                        raise ArchiveGateError("INVALID_PROVENANCE_PATH_SET")
                    _git(worktree, "add", "--", *created)
                    _git(worktree, "-c", "user.name=football-king-archive-pilot",
                         "-c", "user.email=archive-pilot@users.noreply.github.com",
                         "commit", "-m", "Append immutable forecast provenance research batch")
                    # Fixed full ref. Non-force push cannot change main or rewrite history.
                    _git(worktree, "push", "origin", "HEAD:" + ARCHIVE_REF)
                    return {"status": "ARCHIVED_ON_ISOLATED_BRANCH",
                            "branch": ARCHIVE_BRANCH, "new_files": len(created),
                            "production_recommendations": "DISABLED"}
                finally:
                    _git(repo, "worktree", "remove", "--force", str(worktree))
        except ArchiveGateError as exc:
            if str(exc) in ("ARCHIVE_BRANCH_NOT_PROVISIONED", "UNTRUSTED_ARCHIVE_REF",
                            "INVALID_PROVENANCE_PATH_SET", "INVALID_WORKTREE"):
                raise
            if attempt_no == max_tries - 1:
                raise ArchiveGateError("ISOLATED_ARCHIVE_WRITE_NOT_CONFIRMED") from exc
            if retry_sleep:
                time.sleep(retry_sleep)
    raise ArchiveGateError("ISOLATED_ARCHIVE_WRITE_NOT_CONFIRMED")


def append_official(proof, repo, run_id, attempt, day, *, max_tries=3, retry_sleep=0):
    """Future authorized production canary entrypoint: fixed verified origin.

    The generic append function remains available for *local synthetic Git*
    integration fixtures; real GitHub callers must use this gated wrapper.
    Verifying Git configuration is NOT branch-protection evidence.
    """
    verify_archive_writer_origin(repo)
    # A Git branch being present does not make its write access authorized.
    require_independent_hosted_archive_custody()
    result = append(proof, repo, run_id, attempt, day,
                    max_tries=max_tries, retry_sleep=retry_sleep)
    verify_archive_writer_origin(repo)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--day", required=True)
    args = parser.parse_args(argv)
    try:
        result = append_official(args.proof, args.repo, args.run_id, args.attempt, args.day)
    except (ArchiveGateError, ValueError, OSError, subprocess.TimeoutExpired):
        print(json.dumps({"status": "HOLD_ARCHIVE_NOT_CONFIRMED",
                          "production_recommendations": "DISABLED"}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
