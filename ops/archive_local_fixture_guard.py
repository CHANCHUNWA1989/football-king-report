"""Restrict legacy generic archive append helpers to *local bare-Git fixtures*.

The official hosted writer CLI is separately locked. This gate prevents code
that directly imports generic append() from using it as an unofficial remote
GitHub writer. It is NOT a network namespace or filesystem mount attestation.

No HTTP(S), SSH, Git protocol, file:// transport, URL rewrite, push URL,
mirror, remote command overrides, config includes or hooks override.
No network access or git write is used by this check.
"""

from pathlib import Path
import os
import subprocess

from ops.archive_remote_ref_gate import sanitized_git_env


class LocalFixtureOnlyHold(ValueError):
    """No secret-bearing remote names in errors."""


def _local_config(repo, *args):
    try:
        run = subprocess.run(
            ["git", "-C", str(repo), "config", "--local", *args],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=False, text=True, timeout=10,
            env=sanitized_git_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LocalFixtureOnlyHold("LOCAL_FIXTURE_CONFIG_UNVERIFIABLE") from exc
    if run.returncode:
        raise LocalFixtureOnlyHold("LOCAL_FIXTURE_CONFIG_UNVERIFIABLE")
    return run.stdout


def require_local_fixture_git_origin(repo):
    """Verify the generic writer's origin is one ordinary local bare repo.

    This is a conservative static, local-config check rather than proof of
    host isolation. Hosted writers must not invoke the generic append helper.
    """
    repo = Path(repo)
    if not repo.is_dir() or repo.is_symlink():
        raise LocalFixtureOnlyHold("LOCAL_FIXTURE_REPOSITORY_INVALID")
    values = _local_config(repo, "--get-all", "remote.origin.url").splitlines()
    if len(values) != 1:
        raise LocalFixtureOnlyHold("LOCAL_FIXTURE_ORIGIN_NOT_UNIQUE")
    origin = values[0]
    # A real GitHub/remote URL, local relative path, URL scheme or scp-like
    # syntax must never be accepted for the opt-in fixture helper.
    if not origin.startswith("/") or "://" in origin or "\x00" in origin:
        raise LocalFixtureOnlyHold("LOCAL_FIXTURE_REMOTE_NOT_LOCAL_PATH")
    target = Path(origin)
    if not target.is_absolute() or ".." in target.parts:
        raise LocalFixtureOnlyHold("LOCAL_FIXTURE_REMOTE_NOT_LOCAL_PATH")
    # Do not accept symlink aliases to an unreviewed filesystem destination.
    if any(p.is_symlink() for p in (target, *target.parents)):
        raise LocalFixtureOnlyHold("LOCAL_FIXTURE_REMOTE_PATH_UNTRUSTED")
    if not target.is_dir() or not (target / "HEAD").is_file() or not (target / "objects").is_dir():
        raise LocalFixtureOnlyHold("LOCAL_FIXTURE_REMOTE_NOT_BARE_REPOSITORY")
    # We must not let the apparently local origin redirect to GitHub via
    # local Git config. System/global Git config are disabled by env.
    config = _local_config(repo, "--list").splitlines()
    keys = [record.split("=", 1)[0].lower() for record in config]
    forbidden_exact = {
        "remote.origin.pushurl", "remote.origin.mirror",
        "remote.origin.push", "remote.origin.receivepack",
        "remote.origin.uploadpack", "core.hookspath",
    }
    if any(key in forbidden_exact or key.startswith((
            "url.", "include.", "includeif.", "credential."))
           for key in keys):
        raise LocalFixtureOnlyHold("LOCAL_FIXTURE_GIT_REDIRECTION_UNTRUSTED")
    return {
        "status": "LOCAL_BARE_GIT_FIXTURE_ONLY",
        "hosted_archive_write_authorized": False,
        "main_ruleset_activation_authorized": False,
        "production_recommendations": "DISABLED",
    }
