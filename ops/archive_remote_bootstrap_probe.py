"""Read-only real-GitHub archive bootstrap ref probe for a PR CI sandbox.

Never creates/writes/fetches branches or requires an authenticated token.
The ref is initialized but NOT protected, independently witnessed, or trusted.
A successful probe is explicitly NOT permission, Ruleset or release evidence.
"""

import argparse
import json
import os
import re
import subprocess

ARCHIVE_REF = "refs/heads/research/forward-provenance-archive"
REPO_URL = "https://github.com/CHANCHUNWA1989/football-king-report.git"
BOOTSTRAP_SHA = "3ce493fbeb9bfea29af1b93064a085afe8efb280"
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_MAX_BYTES = 1024


class RemoteBootstrapHold(ValueError):
    """No raw status, credentials, token, URL rewrites or response bodies."""


def parse_ref_reply(raw, expected_sha=BOOTSTRAP_SHA):
    """Validate an EXACT single branch advertisement, no substring matching."""
    if not isinstance(raw, bytes) or len(raw) > _MAX_BYTES:
        raise RemoteBootstrapHold("INVALID_REMOTE_REF_RESPONSE")
    if not _SHA.fullmatch(expected_sha):
        raise RemoteBootstrapHold("INVALID_EXPECTED_ARCHIVE_SHA")
    try:
        lines = raw.decode("ascii", "strict").splitlines()
    except UnicodeError as exc:
        raise RemoteBootstrapHold("INVALID_REMOTE_REF_RESPONSE") from exc
    if len(lines) != 1:
        raise RemoteBootstrapHold("AMBIGUOUS_OR_MISSING_REMOTE_REF")
    fields = lines[0].split()
    if len(fields) != 2 or not _SHA.fullmatch(fields[0]) or fields[1] != ARCHIVE_REF:
        raise RemoteBootstrapHold("UNTRUSTED_REMOTE_REF_ADVERTISEMENT")
    if fields[0] != expected_sha:
        raise RemoteBootstrapHold("REMOTE_ARCHIVE_REF_DRIFT_FROM_BOOTSTRAP")
    return {
        "status": "REMOTE_BOOTSTRAP_SHA_OBSERVED_READ_ONLY_NOT_PROTECTED",
        "archive_ref": ARCHIVE_REF,
        "archive_sha": fields[0],
        "expected_bootstrap_sha": expected_sha,
        "read_only_probe": True,
        "effective_branch_protection_verified": False,
        "independent_review_verified": False,
        "remote_canary_write_verified": False,
        "source_data_authenticity_verified": False,
        "production_recommendations": "DISABLED",
    }


def _git_environment():
    # The probe runs without any OAuth token, checkout credentials or secrets.
    # Drop Git env configuration overrides and Git tracing.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env.update({"GIT_TERMINAL_PROMPT": "0",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_SYSTEM": os.devnull,
                "GIT_OPTIONAL_LOCKS": "0"})
    return env


def check_remote_bootstrap():
    """Read exact public GitHub archive ref once; NO git fetch or push."""
    try:
        result = subprocess.run([
            "git", "ls-remote", "--exit-code", "--heads",
            REPO_URL, ARCHIVE_REF,
        ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=False, timeout=20, env=_git_environment())
    except (OSError, subprocess.SubprocessError) as exc:
        raise RemoteBootstrapHold("REMOTE_REF_READ_UNAVAILABLE") from exc
    if result.returncode:
        raise RemoteBootstrapHold("REMOTE_REF_READ_UNAVAILABLE")
    return parse_ref_reply(result.stdout)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-only", action="store_true", required=True,
                        help="Only observes a public pinned archive ref; never writes")
    parser.parse_args(argv)
    try:
        print(json.dumps(check_remote_bootstrap(), sort_keys=True))
        return 0
    except RemoteBootstrapHold:
        print(json.dumps({
            "status": "HOLD_REMOTE_ARCHIVE_BOOTSTRAP_NOT_CONFIRMED",
            "effective_branch_protection_verified": False,
            "remote_canary_write_verified": False,
            "production_recommendations": "DISABLED",
        }, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
