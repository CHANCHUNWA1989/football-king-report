"""Read-only governance readiness diagnostic for original-A double attestations.

Mirrors the strict independent-review / protected-main guardrails from Draft
PR #438 (ops/vnext_pr09_signer_preflight.py). This is only a diagnostic; it
NEVER signs, deploys, promotes or enables a canary. A signature witness
preflight is a separate step and must itself use genuine gh verification.
"""
import argparse
from datetime import datetime
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO = "CHANCHUNWA1989/football-king-report"
REPO_ID = "1411226578"
PR_ID = 458
ACTIONS_APP_ID = 15368
REQUIRED = frozenset(("safety (3.11)", "safety (3.12)",
                      "validate", "ledger-tests"))
SIGNER = ".github/workflows/football-king-a-same-get-provenance.yml"
SCHEMA = "football-king-a-two-signer-governance-readiness-v1"
MAX_API = 262144

ENDPOINTS = {
    "branch": f"/repos/{REPO}/branches/main",
    "protection": f"/repos/{REPO}/branches/main/protection",
    "rulesets": f"/repos/{REPO}/rulesets",
    "signer_workflow": f"/repos/{REPO}/contents/{SIGNER}?ref=main",
    "pr": f"/repos/{REPO}/pulls/{PR_ID}",
    "reviews": f"/repos/{REPO}/pulls/{PR_ID}/reviews?per_page=100",
}


class ReadUnavailable(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def github_reader(token=None):
    """Fixed host, fixed GET-only paths; no write or user-selected URL."""
    def get(path):
        if path not in ENDPOINTS.values():
            raise ReadUnavailable("UNAPPROVED_GITHUB_API_PATH")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "football-king-a-governance-readonly",
        }
        if token:
            headers["Authorization"] = "Bearer " + token
        req = Request("https://api.github.com" + path,
                      headers=headers, method="GET")
        try:
            with urlopen(req, timeout=12) as result:
                body = result.read(MAX_API + 1)
            if not 0 < len(body) <= MAX_API:
                raise ReadUnavailable("EMPTY_OR_OVERSIZED_GITHUB_REPLY")
            parsed = json.loads(body)
            if type(parsed) not in (list, dict):
                raise ReadUnavailable("INVALID_GITHUB_REPLY_TYPE")
            return parsed
        except HTTPError as exc:
            if exc.code == 403:
                raise ReadUnavailable("GITHUB_ADMIN_READ_FORBIDDEN") from None
            if exc.code == 404:
                raise ReadUnavailable("GITHUB_RESOURCE_NOT_FOUND") from None
            raise ReadUnavailable("GITHUB_READ_UNAVAILABLE") from None
        except (URLError, OSError, UnicodeError, ValueError) as exc:
            if isinstance(exc, ReadUnavailable):
                raise
            raise ReadUnavailable("GITHUB_READ_UNAVAILABLE") from None
    return get


def snapshot(fetch):
    """Collect all fixed reads; one blocker cannot mask another."""
    result = {}
    for key, path in ENDPOINTS.items():
        try:
            result[key] = fetch(path)
        except Exception as exc:
            result[key] = {
                "_error": exc.code if type(exc) is ReadUnavailable else
                          "GITHUB_READ_UNAVAILABLE"
            }
    return result


def _error(x):
    return x.get("_error") if type(x) is dict else None


def _sha(x):
    return type(x) is str and re.fullmatch("[0-9a-f]{40}", x) is not None


def _check_protection(value, blockers):
    if _error(value):
        blockers.append("PROTECTION_READ_UNAVAILABLE")
        return
    if type(value) is not dict:
        blockers.append("PROTECTION_READ_UNAVAILABLE")
        return
    reviews = value.get("required_pull_request_reviews")
    if type(reviews) is not dict:
        blockers.append("INDEPENDENT_APPROVAL_NOT_REQUIRED")
    else:
        if (type(reviews.get("required_approving_review_count")) is not int
                or reviews["required_approving_review_count"] < 1):
            blockers.append("INDEPENDENT_APPROVAL_NOT_REQUIRED")
        if reviews.get("dismiss_stale_reviews") is not True:
            blockers.append("STALE_REVIEWS_NOT_DISMISSED")
        if reviews.get("require_last_push_approval") is not True:
            blockers.append("LAST_PUSH_APPROVAL_NOT_REQUIRED")
        # GitHub branch protection may permit named people/apps to bypass
        # pull-request review despite requiring one on paper. Empty/null is
        # acceptable; a non-empty or malformed exception is not.
        allowances = reviews.get("bypass_pull_request_allowances")
        if allowances is not None:
            if (type(allowances) is not dict or
                    any(type(allowances.get(k)) is not list or allowances[k]
                        for k in ("users", "teams", "apps"))):
                blockers.append("REVIEW_BYPASS_ALLOWANCE_PRESENT_OR_UNREADABLE")
    if (type(value.get("enforce_admins")) is not dict or
            value["enforce_admins"].get("enabled") is not True):
        blockers.append("ADMIN_BYPASS_NOT_BLOCKED")
    checks = value.get("required_status_checks")
    if type(checks) is not dict or checks.get("strict") is not True:
        blockers.append("STRICT_REQUIRED_CI_NOT_ENFORCED")
    else:
        items = checks.get("checks")
        if type(items) is not list or not items:
            blockers.append("APP_PINNED_CI_NOT_AVAILABLE")
        else:
            pinned = {}
            malformed = False
            for entry in items:
                if (type(entry) is not dict or
                        type(entry.get("context")) is not str or
                        type(entry.get("app_id")) is not int):
                    malformed = True
                    continue
                name = entry["context"]
                if name in pinned and pinned[name] != entry["app_id"]:
                    malformed = True
                pinned[name] = entry["app_id"]
            if malformed:
                blockers.append("APP_PINNED_CI_MALFORMED_OR_AMBIGUOUS")
            if not REQUIRED.issubset(pinned):
                blockers.append("MANDATORY_CI_CHECKS_MISSING")
            elif any(pinned[name] != ACTIONS_APP_ID for name in REQUIRED):
                blockers.append("MANDATORY_CI_NOT_PINNED_TO_GITHUB_ACTIONS")
    for key, failure in (
        ("allow_force_pushes", "FORCE_PUSHES_NOT_BLOCKED"),
        ("allow_deletions", "BRANCH_DELETION_NOT_BLOCKED"),
    ):
        x = value.get(key)
        if type(x) is not dict or x.get("enabled") is not False:
            blockers.append(failure)


def _review_ok(pr, reviews):
    if (type(pr) is not dict or type(reviews) is not list
            or len(reviews) > 100 or type(pr.get("head")) is not dict):
        return False
    head = pr["head"].get("sha")
    author = pr.get("user")
    if (not _sha(head) or type(author) is not dict
            or type(author.get("login")) is not str):
        return False
    most_recent = {}
    for row in reviews:
        if (type(row) is not dict or type(row.get("user")) is not dict
                or type(row["user"].get("login")) is not str
                or type(row.get("state")) is not str):
            return False
        login = row["user"]["login"]
        # GitHub API lists reviews chronologically. Use latest non-pending
        # submitted review for each human, never an older stale approval.
        if row["state"] != "PENDING":
            most_recent[login] = row
    if len(reviews) == 100 or any(
            review["state"] == "CHANGES_REQUESTED"
            for review in most_recent.values()
        ):
        return False
    return any(
        login != author["login"]
        and value["user"].get("type") == "User"
        and value["state"] == "APPROVED"
        and value.get("commit_id") == head
        for login, value in most_recent.items()
    )


def assess(data, *, context=None):
    """Pure fail-closed policy assessment; no bypass or signer execution."""
    blockers = []
    if type(data) is not dict or set(data) != set(ENDPOINTS):
        return _report(["GOVERNANCE_EVIDENCE_INCOMPLETE"])
    branch = data["branch"]
    if _error(branch) or type(branch) is not dict:
        blockers.append("MAIN_BRANCH_METADATA_UNAVAILABLE")
        main_sha = None
    else:
        main_sha = branch.get("commit", {}).get("sha") if type(branch.get("commit")) is dict else None
        if branch.get("name") != "main" or not _sha(main_sha):
            blockers.append("MAIN_BRANCH_METADATA_INVALID")
        if branch.get("protected") is not True:
            blockers.append("MAIN_NOT_PROTECTED")
    _check_protection(data["protection"], blockers)
    rulesets = data["rulesets"]
    # The predecessor PR-09 preflight relies on active branch protection.
    # A ruleset cannot be used as an undocumented substitute or bypass.
    if _error(rulesets) or type(rulesets) is not list:
        blockers.append("RULESETS_INSPECTION_UNAVAILABLE")
    elif rulesets:
        blockers.append("RULESET_BYPASS_SCOPE_UNREVIEWED")
    signer = data["signer_workflow"]
    if _error(signer) or type(signer) is not dict:
        blockers.append("APPROVED_MAIN_SIGNER_WORKFLOW_ABSENT")
    elif (signer.get("path") != SIGNER
          or signer.get("type") != "file" or
          type(signer.get("size")) is not int or
          not 0 < signer["size"] <= 200000 or
          not _sha(signer.get("sha", ""))):
        blockers.append("APPROVED_MAIN_SIGNER_WORKFLOW_INVALID")
    pr = data["pr"]
    if _error(pr) or type(pr) is not dict:
        blockers.append("RESEARCH_PR_STATUS_UNAVAILABLE")
    else:
        if (pr.get("number") != PR_ID or pr.get("state") != "open"
                or pr.get("draft") is not False or
                pr.get("merged") is not False):
            blockers.append("RESEARCH_PR_NOT_READY_FOR_APPROVAL")
    reviews = data["reviews"]
    if _error(reviews) or not _review_ok(pr, reviews):
        blockers.append("CURRENT_HEAD_INDEPENDENT_HUMAN_APPROVAL_MISSING")
    if context is not None:
        must = {
            "GITHUB_REPOSITORY": REPO,
            "GITHUB_REPOSITORY_ID": REPO_ID,
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_REF_TYPE": "branch",
        }
        if type(context) is not dict or any(context.get(k) != v for k, v in must.items()):
            blockers.append("NOT_AN_APPROVED_MANUAL_MAIN_RUN")
        elif context.get("GITHUB_SHA") != main_sha or not _sha(main_sha):
            blockers.append("MAIN_SHA_DRIFT_OR_UNTRUSTED_SIGNER_RUN")
    return _report(blockers, main_sha=main_sha)


def _report(blockers, *, main_sha=None):
    blockers = sorted(set(blockers))
    return {
        "schema": SCHEMA, "status": "HOLD",
        "production_recommendations": "DISABLED",
        "governance_diagnostic_completed": True,
        "governance_preflight_requirements_observed": not bool(blockers),
        "governance_blocker_codes": blockers,
        "main_commit_observed": main_sha if _sha(main_sha) else None,
        "approved_main_signer_enabled": False,
        "real_signatures_verified": False,
        "actual_live_capture_authorized": False,
        "data_rights_verified": False,
        "independently_verified_results": False,
        "certified_prospective_samples": 0,
        "positive_ev_verified": False,
        "model_promoted": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-readonly", action="store_true")
    parser.add_argument("--require-hold", action="store_true")
    args = parser.parse_args(argv)
    if not args.live_readonly:
        parser.error("Only --live-readonly is supported; no signer or write operation")
    records = snapshot(github_reader(os.getenv("GITHUB_TOKEN") or None))
    report = assess(records, context=dict(os.environ))
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    if args.require_hold:
        # CI can exercise the truly external read-only state without assuming
        # or enforcing an unprotected repo forever. Status is *always* HOLD.
        return 0 if report["status"] == "HOLD" and not report["approved_main_signer_enabled"] else 1
    return 0 if report["governance_preflight_requirements_observed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
