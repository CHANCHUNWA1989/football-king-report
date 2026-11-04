"""PR-09: fail-closed governance preflight for the synthetic-only PR-08 signer.

This does NOT certify any actual Sigstore signature, data licence, forecast,
real result, out-of-sample performance, EV, or permission to trade.

Only an independently configured protected main branch may run the synthetic
signer. Missing GitHub protection API permission is a BLOCKER, not a bypass.
"""
import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO = "CHANCHUNWA1989/football-king-report"
REPO_ID = "1411226578"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
BRANCH_ENDPOINT = f"/repos/{REPO}/branches/main"
PROTECTION_ENDPOINT = BRANCH_ENDPOINT + "/protection"
MAX_RESPONSE_BYTES = 131_072


class GovernanceHold(ValueError):
    """Non-promotable verification failure with stable, non-secret code."""


def _require(condition, reason):
    if not condition:
        raise GovernanceHold(reason)


def _enabled(mapping, key):
    item = mapping.get(key) if type(mapping) is dict else None
    return type(item) is dict and item.get("enabled") is True


def assess_preflight(context, fetch_json):
    """Evaluate a pinned workflow context and authoritative GitHub API reads.

    fetch_json is only called with the two fixed API paths above. The caller
    supplies no repository, host, ref, or security-policy override.
    """
    _require(type(context) is dict, "INVALID_WORKFLOW_CONTEXT")
    must_equal = {
        "GITHUB_REPOSITORY": REPO,
        "GITHUB_REPOSITORY_ID": REPO_ID,
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REF_TYPE": "branch",
    }
    for key, value in must_equal.items():
        _require(context.get(key) == value, "UNTRUSTED_WORKFLOW_CONTEXT")
    sha = context.get("GITHUB_SHA")
    _require(type(sha) is str and SHA40.fullmatch(sha), "INVALID_RUN_COMMIT_SHA")
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        val = context.get(key)
        _require(type(val) is str and val.isascii() and val.isdecimal()
                 and 0 < int(val) < 10**15, "INVALID_RUN_IDENTITY")

    branch = fetch_json(BRANCH_ENDPOINT)
    _require(type(branch) is dict, "INVALID_BRANCH_METADATA")
    _require(branch.get("name") == "main", "WRONG_BRANCH_METADATA")
    commit = branch.get("commit")
    _require(type(commit) is dict and commit.get("sha") == sha,
             "MAIN_HEAD_DRIFT_OR_WRONG_COMMIT")
    _require(branch.get("protected") is True, "MAIN_BRANCH_NOT_PROTECTED")

    # The branch metadata 'protected' bit is NOT sufficient: it might be
    # satisfied by rules that do not require code review or status checks.
    # A 403 when reading /protection must therefore fail closed.
    protection = fetch_json(PROTECTION_ENDPOINT)
    _require(type(protection) is dict, "INVALID_BRANCH_PROTECTION")
    reviews = protection.get("required_pull_request_reviews")
    _require(type(reviews) is dict, "INDEPENDENT_REVIEW_NOT_REQUIRED")
    count = reviews.get("required_approving_review_count")
    _require(type(count) is int and count >= 1,
             "INDEPENDENT_REVIEW_NOT_REQUIRED")
    _require(reviews.get("dismiss_stale_reviews") is True,
             "STALE_APPROVALS_NOT_DISMISSED")
    _require(reviews.get("require_last_push_approval") is True,
             "LAST_PUSH_REVIEW_NOT_REQUIRED")
    _require(_enabled(protection, "enforce_admins"),
             "ADMINS_BYPASS_PROTECTION")
    status = protection.get("required_status_checks")
    _require(type(status) is dict and status.get("strict") is True,
             "STRICT_REQUIRED_CI_MISSING")
    checks = status.get("checks")
    contexts = status.get("contexts")
    _require((type(checks) is list and len(checks) > 0)
             or (type(contexts) is list and len(contexts) > 0),
             "NO_REQUIRED_STATUS_CHECKS")
    _require(type(protection.get("allow_force_pushes")) is dict
             and protection["allow_force_pushes"].get("enabled") is False,
             "FORCE_PUSH_PROTECTION_UNVERIFIED")
    _require(type(protection.get("allow_deletions")) is dict
             and protection["allow_deletions"].get("enabled") is False,
             "BRANCH_DELETE_PROTECTION_UNVERIFIED")

    return {
        "status": "SYNTHETIC_SIGNER_GOVERNANCE_PREFLIGHT_OK",
        "checked_main_commit": sha,
        "required_approving_reviews": count,
        "real_data_licence_verified": False,
        "real_signature_verified": False,
        "model_scoring_eligible": False,
        "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
    }


def github_api_fetch(token):
    """Create a fixed-host, fixed-path JSON reader. Network failure => HOLD."""
    _require(type(token) is str and bool(token.strip()),
             "GITHUB_READ_TOKEN_MISSING")

    def read(path):
        _require(path in (BRANCH_ENDPOINT, PROTECTION_ENDPOINT),
                 "UNAPPROVED_GITHUB_API_PATH")
        req = Request(
            "https://api.github.com" + path,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + token,
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "football-king-synthetic-governance-gate",
            },
            method="GET",
        )
        try:
            with urlopen(req, timeout=12) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            _require(0 < len(raw) <= MAX_RESPONSE_BYTES,
                     "GITHUB_GOVERNANCE_RESPONSE_SIZE")
            result = json.loads(raw)
            _require(type(result) is dict, "GITHUB_GOVERNANCE_RESPONSE_FORMAT")
            return result
        except (HTTPError, URLError, OSError, ValueError, UnicodeError) as exc:
            raise GovernanceHold("GITHUB_GOVERNANCE_API_UNAVAILABLE") from exc
    return read


def main():
    try:
        result = assess_preflight(
            dict(os.environ), github_api_fetch(os.getenv("GH_TOKEN", "")))
    except (GovernanceHold, KeyError, TypeError, OverflowError) as exc:
        reason = str(exc) if type(exc) is GovernanceHold else "GOVERNANCE_PREFLIGHT_FAILED"
        print(f"HOLD: synthetic signer preflight denied: {reason}", file=sys.stderr)
        return 1
    print("Governance preflight accepted for SYNTHETIC canary only.")
    print("No real data rights, real signature, model validation or EV inferred.")
    print("Production recommendations:", result["production_recommendations"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
