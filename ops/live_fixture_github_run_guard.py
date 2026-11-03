"""Fresh GitHub Actions run-metadata corroboration for fixture-witness research.

No saved run.json or caller-provided 'run_verified' flag is accepted.
The CLI reads GitHub's live REST run record using an authenticated gh session,
and checks a fixed repo, branch, workflow path, source commit, run attempt,
event, outcome and server timestamps before the RECORDED kickoff.

This is not independent confirmation that the football fixture/kickoff,
upstream sources, corners or bookmaker quotes are genuine.
"""
from datetime import datetime, timedelta, timezone
import json
import re
import subprocess

from live_fixture_attestation_audit import _timestamp

REPOSITORY = "CHANCHUNWA1989/football-king-report"
REPOSITORY_ID = 1411226578
WORKFLOW = ".github/workflows/football-king-live-fixture-seal.yml"
MAX_RESPONSE_BYTES = 256_000


def _hold(reason):
    return {
        "status": "HOLD",
        "reason": reason,
        "github_run_metadata_correlated": False,
        "actual_kickoff_authenticated": False,
        "fixture_source_authenticated": False,
        "market_executable_verified": False,
        "certified_positive_ev": False,
        "production_recommendations": "DISABLED",
    }


def _json_unique_pairs(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("DUPLICATE_GITHUB_RUN_KEY")
        output[key] = value
    return output


def _bad_number(_):
    raise ValueError("NONFINITE_GITHUB_RUN_JSON")


def _same_repo(value):
    return (type(value) is dict
            and type(value.get("id")) is int
            and value["id"] == REPOSITORY_ID
            and value.get("full_name") == REPOSITORY)


def _required_time(value):
    return _timestamp(value)


def audit_github_run(*, source_sha, run_id, attempt, recorded_kickoff_utc, now=None):
    """Return RESEARCH_ONLY only after *fresh* authenticated GitHub API read."""
    try:
        if (type(source_sha) is not str
                or re.fullmatch(r"[0-9a-f]{40}", source_sha) is None
                or type(run_id) is not str
                or re.fullmatch(r"[1-9][0-9]{0,19}", run_id) is None
                or type(attempt) is not str
                or re.fullmatch(r"[1-9][0-9]{0,4}", attempt) is None):
            return _hold("INVALID_GITHUB_RUN_PINS")
        current = datetime.now(timezone.utc) if now is None else now
        if (not isinstance(current, datetime) or current.tzinfo is None
                or current.utcoffset() is None):
            return _hold("INVALID_AUDIT_CLOCK")
        current = current.astimezone(timezone.utc)
        kickoff = _required_time(recorded_kickoff_utc)
        argv = [
            "gh", "api", "--hostname", "github.com", "--method", "GET",
            f"/repos/{REPOSITORY}/actions/runs/{run_id}",
        ]
        try:
            completed = subprocess.run(
                argv, capture_output=True, shell=False, timeout=20, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return _hold("GITHUB_API_UNAVAILABLE")
        if completed.returncode != 0:
            return _hold("GITHUB_API_RUN_REJECTED")
        raw = completed.stdout
        if (type(raw) is not bytes or not raw or len(raw) > MAX_RESPONSE_BYTES):
            return _hold("INVALID_GITHUB_API_RESPONSE_SIZE")
        try:
            run = json.loads(raw, object_pairs_hook=_json_unique_pairs,
                             parse_constant=_bad_number)
        except (UnicodeError, ValueError, TypeError, RecursionError):
            return _hold("INVALID_GITHUB_API_JSON")
        if type(run) is not dict:
            return _hold("INVALID_GITHUB_RUN_OBJECT")
        if (not _same_repo(run.get("repository"))
                or not _same_repo(run.get("head_repository"))
                or type(run.get("id")) is not int
                or run["id"] != int(run_id)):
            return _hold("GITHUB_RUN_REPOSITORY_OR_ID_MISMATCH")
        if (type(run.get("run_attempt")) is not int
                or run["run_attempt"] != int(attempt)
                or run.get("path") != WORKFLOW
                or run.get("head_branch") != "main"
                or run.get("head_sha") != source_sha
                or run.get("event") != "workflow_dispatch"):
            return _hold("GITHUB_RUN_SOURCE_CONTEXT_MISMATCH")
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            return _hold("GITHUB_RUN_NOT_SUCCESSFUL")
        created = _required_time(run.get("created_at"))
        started = _required_time(run.get("run_started_at"))
        # GH metadata corroborates when this run was scheduled/started.
        # It does not establish the true kickoff, which still comes from
        # the submitted fixture manifest.
        if not (created <= started <= current + timedelta(minutes=5)):
            return _hold("GITHUB_RUN_CLOCK_ORDER_INVALID")
        if started > kickoff - timedelta(minutes=10):
            return _hold("GITHUB_RUN_NOT_STARTED_EARLY_ENOUGH")
        return {
            **_hold("GITHUB_RUN_MATCHES_PINNED_RESEARCH_CONTEXT"),
            "status": "RESEARCH_ONLY",
            "github_run_metadata_correlated": True,
        }
    except (ValueError, TypeError, OverflowError, KeyError, AttributeError):
        return _hold("GITHUB_RUN_DATA_OR_TIME_INVALID")
