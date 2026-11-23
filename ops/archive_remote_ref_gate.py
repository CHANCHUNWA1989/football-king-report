"""Read-only, fail-closed Git remote-ref correlation for archive research.

This checks which commit a specific remote Git branch *currently* advertises.
It is NOT an independent signature, trusted timestamp or GitHub Ruleset proof.
No fetch, push, branch creation or credential setup is performed.
"""

import os
from pathlib import Path
import re
import subprocess

ARCHIVE_REF = "refs/heads/research/forward-provenance-archive"
OFFICIAL_ORIGIN = "https://github.com/CHANCHUNWA1989/football-king-report.git"
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")


class RemoteRefHold(ValueError):
    """Safe rejection without leaking remote response/credential details."""


def sanitized_git_env():
    """Avoid inherited Git overrides on all archive read/write Git subprocesses.

    Credential/header handling still requires independent runner review. The
    snapshot of environment alone does not establish remote GitHub identity.
    """
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("GIT_") and k != "GIT_CURL_VERBOSE"}
    env.update({"GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0",
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_SYSTEM": os.devnull})
    return env


def _git(repo, *args):
    # This is a local integrity precondition, not independently witnessed
    # GitHub identity, hosted branch protection or a signature.
    env = sanitized_git_env()
    try:
        result = subprocess.run(["git", "-C", str(repo), *args],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL,
                                text=True, check=False, timeout=20, env=env)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RemoteRefHold("ARCHIVE_REMOTE_LOOKUP_FAILED") from exc
    if result.returncode:
        raise RemoteRefHold("ARCHIVE_REMOTE_LOOKUP_FAILED")
    return result.stdout.strip()


def _verify_fixed_remote(repo, expected_sha, trusted_url):
    """Core for genuine offline bare-Git fixtures; only official wrapper is
    intended for a future authenticated production integration."""
    repo = Path(repo)
    if (not isinstance(expected_sha, str) or not _SHA40.fullmatch(expected_sha)
            or not isinstance(trusted_url, str) or not trusted_url
            or not repo.is_dir() or repo.is_symlink()):
        raise RemoteRefHold("INVALID_ARCHIVE_REMOTE_CONFIGURATION")
    try:
        top = Path(_git(repo, "rev-parse", "--show-toplevel")).resolve()
    except RemoteRefHold as exc:
        raise RemoteRefHold("ARCHIVE_CHECKOUT_NOT_REPOSITORY_ROOT") from exc
    if top != repo.resolve():
        raise RemoteRefHold("ARCHIVE_CHECKOUT_NOT_REPOSITORY_ROOT")
    try:
        head = _git(repo, "rev-parse", "--verify", "HEAD")
        origin = _git(repo, "config", "--local", "--get", "remote.origin.url")
    except RemoteRefHold as exc:
        raise RemoteRefHold("ARCHIVE_REMOTE_IDENTITY_NOT_VERIFIED") from exc
    if head != expected_sha:
        raise RemoteRefHold("ARCHIVE_LOCAL_HEAD_MISMATCH")
    if origin != trusted_url:
        raise RemoteRefHold("ARCHIVE_ORIGIN_MISMATCH")
    # Git's url.<base>.insteadOf and include.* settings can redirect an
    # apparently correct origin URL to a different endpoint. Refuse these
    # in the local repo; disregard system and global config in _git.
    local_config = _git(repo, "config", "--local", "--list")
    keys = [entry.split("=", 1)[0].lower() for entry in local_config.splitlines()]
    if any(key.startswith(("url.", "include.", "includeif.")) for key in keys):
        raise RemoteRefHold("ARCHIVE_GIT_URL_REWRITE_UNTRUSTED")
    # Never use attacker-supplied 'origin', arbitrary branch args, or a
    # locally cached origin/<branch> ref as remote-head evidence.
    try:
        lines = _git(repo, "ls-remote", "--exit-code", "--heads",
                     trusted_url, ARCHIVE_REF).splitlines()
    except RemoteRefHold as exc:
        raise RemoteRefHold("ARCHIVE_REMOTE_REF_NOT_CONFIRMED") from exc
    fields = lines[0].split() if len(lines) == 1 else []
    if (len(fields) != 2 or not _SHA40.fullmatch(fields[0])
            or fields[1] != ARCHIVE_REF or fields[0] != expected_sha):
        raise RemoteRefHold("ARCHIVE_REMOTE_REF_MISMATCH")
    return {
        "status": "REMOTE_BRANCH_SHA_CORRELATED_NOT_ATTESTED",
        "archive_ref": ARCHIVE_REF,
        "archive_head_sha": expected_sha,
        "remote_ref_checked": True,
        "remote_identity_independently_attested": False,
        "trusted_timestamp_verified": False,
        "production_recommendations": "DISABLED",
    }



def verify_archive_writer_origin(repo, *, trusted_url=OFFICIAL_ORIGIN):
    """No-write preflight for archive writers; require one fixed push target.

    Reject Git options that may silently redirect git push origin to another
    repository (pushurl, mirror, URL rewrite, config includes).
    A matching URL is only local configuration evidence, NOT proof of
    effective GitHub branch protection or actor scope.
    """
    repo = Path(repo)
    if (not repo.is_dir() or repo.is_symlink()
            or not isinstance(trusted_url, str) or not trusted_url):
        raise RemoteRefHold("INVALID_ARCHIVE_WRITER_REPOSITORY")
    try:
        top = Path(_git(repo, "rev-parse", "--show-toplevel")).resolve()
    except RemoteRefHold as exc:
        raise RemoteRefHold("ARCHIVE_WRITER_NOT_REPOSITORY_ROOT") from exc
    if top != repo.resolve():
        raise RemoteRefHold("ARCHIVE_WRITER_NOT_REPOSITORY_ROOT")
    try:
        origin = _git(repo, "config", "--local", "--get", "remote.origin.url")
        config = _git(repo, "config", "--local", "--list")
    except RemoteRefHold as exc:
        raise RemoteRefHold("ARCHIVE_WRITER_ORIGIN_NOT_VERIFIED") from exc
    if origin != trusted_url:
        raise RemoteRefHold("ARCHIVE_WRITER_ORIGIN_MISMATCH")
    keys = [line.split("=", 1)[0].lower() for line in config.splitlines()]
    rejected = ("remote.origin.pushurl", "remote.origin.mirror",
                "remote.origin.receivepack", "remote.origin.uploadpack",
                "core.hookspath")
    if any(k in rejected or k.startswith(("url.", "include.", "includeif."))
           for k in keys):
        raise RemoteRefHold("ARCHIVE_WRITER_PUSH_REDIRECTION_UNTRUSTED")
    # Check the exact ref exists now, with explicit target; never bootstrap.
    try:
        lines = _git(repo, "ls-remote", "--exit-code", "--heads",
                     trusted_url, ARCHIVE_REF).splitlines()
    except RemoteRefHold as exc:
        raise RemoteRefHold("ARCHIVE_WRITER_REMOTE_REF_NOT_CONFIRMED") from exc
    fields = lines[0].split() if len(lines) == 1 else []
    if (len(fields) != 2 or not _SHA40.fullmatch(fields[0])
            or fields[1] != ARCHIVE_REF):
        raise RemoteRefHold("ARCHIVE_WRITER_REMOTE_REF_NOT_CONFIRMED")
    return {
        "status": "ARCHIVE_WRITER_REF_OBSERVED_NOT_AUTHORIZED",
        "archive_ref": ARCHIVE_REF,
        "remote_head_sha": fields[0],
        "push_target_config_verified": True,
        "effective_branch_protection_verified": False,
        "independent_review_verified": False,
        "production_recommendations": "DISABLED",
    }


def verify_official_archive_ref(repo, expected_sha):
    """Require the hard-coded repository HTTPS origin and exact archive ref."""
    return _verify_fixed_remote(repo, expected_sha, OFFICIAL_ORIGIN)
