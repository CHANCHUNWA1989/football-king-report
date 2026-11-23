"""Offline-only pilot: archive NDR/OpenLiga raw capture bytes to local bare Git.

Completes test coverage for the two shadow-daily direct-main archive families,
but DOES NOT change live workflow or permit hosted GitHub archive writes.
The public GitHub archive branch exists but has unverified branch rules,
independent review and writer custody: this entrypoint is local fixture ONLY.
"""

from pathlib import Path
import re
import tempfile

from ops.archive_local_fixture_guard import require_local_fixture_git_origin
from ops.archive_ndr_capture_provenance import archive as prepare_ndr
from ops.archive_openliga_capture import prepare as prepare_openliga
from ops.isolated_provenance_archive import (
    ARCHIVE_BRANCH, ARCHIVE_REF, TRACKING_REF, ArchiveGateError, _git, _remote_head,
)

_FAMILIES = {
    "ndr": ("ndr_capture_provenance", prepare_ndr),
    "openliga": ("openliga_capture_provenance", prepare_openliga),
}
_SHA = re.compile(r"[0-9a-f]{40}\Z")


def _main_remote_sha(repo):
    fields = _git(repo, "ls-remote", "--exit-code", "--heads", "origin",
                  "refs/heads/main").splitlines()
    parts = fields[0].split() if len(fields) == 1 else []
    if len(parts) != 2 or not _SHA.fullmatch(parts[0]) or parts[1] != "refs/heads/main":
        raise ArchiveGateError("LOCAL_FIXTURE_MAIN_SHA_NOT_VERIFIED")
    return parts[0]


def append_capture(proof, repo, run_id, attempt, day, *, kind, max_tries=1):
    """Append exactly one complete two-file capture batch to a LOCAL fixture.

    Genuine synthetic bare-Git integration only. No origin rewrites, no
    credentials, no GitHub URL, no main writes, no force push, no ref creation.
    """
    if kind not in _FAMILIES:
        raise ArchiveGateError("INVALID_CAPTURE_FAMILY")
    if max_tries not in (1, 2, 3):
        raise ArchiveGateError("INVALID_CAPTURE_RETRY_POLICY")
    repo, proof = Path(repo), Path(proof)
    require_local_fixture_git_origin(repo)
    before_main = _main_remote_sha(repo)
    folder, prepare = _FAMILIES[kind]
    for retry in range(max_tries):
        # Check every retry, since the origin may have changed after a failure.
        require_local_fixture_git_origin(repo)
        before_archive = _remote_head(repo)
        _git(repo, "fetch", "--no-tags", "origin",
             "+" + ARCHIVE_REF + ":" + TRACKING_REF)
        if _git(repo, "rev-parse", TRACKING_REF) != before_archive:
            raise ArchiveGateError("CONCURRENT_CAPTURE_ARCHIVE_REF_CHANGED")
        with tempfile.TemporaryDirectory(prefix="fk-local-capture-only-") as tmp:
            checkout = Path(tmp) / "checkout"
            _git(repo, "worktree", "add", "--detach", str(checkout), before_archive)
            try:
                result = prepare(proof, checkout, run_id, attempt, day=day)
                paths = result["created"] if kind == "ndr" else result
                if not paths:
                    if _main_remote_sha(repo) != before_main:
                        raise ArchiveGateError("LOCAL_FIXTURE_MAIN_CHANGED")
                    return {
                        "status": "ALREADY_ARCHIVED",
                        "branch": ARCHIVE_BRANCH,
                        "kind": kind,
                        "new_files": 0,
                        "hosted_archive_write_authorized": False,
                        "production_recommendations": "DISABLED",
                    }
                prefix = folder + "/"
                if (len(paths) != 2 or len(set(paths)) != 2
                        or any(not item.startswith(prefix) or not item.endswith(".gz")
                               for item in paths)):
                    raise ArchiveGateError("INVALID_CAPTURE_ARCHIVE_PATH_SET")
                _git(checkout, "add", "--", *paths)
                _git(checkout,
                     "-c", "user.name=football-king-offline-capture-fixture",
                     "-c", "user.email=fixture@users.noreply.github.com",
                     "commit", "-m", "Offline synthetic capture fixture only")
                require_local_fixture_git_origin(repo)
                if _main_remote_sha(repo) != before_main:
                    raise ArchiveGateError("LOCAL_FIXTURE_MAIN_CHANGED")
                try:
                    _git(checkout, "push", "origin", "HEAD:" + ARCHIVE_REF)
                except ArchiveGateError as exc:
                    if retry == max_tries - 1:
                        raise ArchiveGateError("LOCAL_CAPTURE_ARCHIVE_PUSH_NOT_CONFIRMED") from exc
                    continue
                if _main_remote_sha(repo) != before_main:
                    raise ArchiveGateError("LOCAL_FIXTURE_MAIN_CHANGED")
                return {
                    "status": "CAPTURE_ARCHIVED_LOCAL_FIXTURE_ONLY",
                    "branch": ARCHIVE_BRANCH,
                    "kind": kind,
                    "new_files": len(paths),
                    "hosted_archive_write_authorized": False,
                    "production_recommendations": "DISABLED",
                }
            finally:
                _git(repo, "worktree", "remove", "--force", str(checkout))
    raise ArchiveGateError("LOCAL_CAPTURE_ARCHIVE_PUSH_NOT_CONFIRMED")
