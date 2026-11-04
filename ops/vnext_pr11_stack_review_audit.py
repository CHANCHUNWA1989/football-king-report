"""PR-11 read-only release-review evidence inventory for the unmerged VNext stack.

No merge, approval, deployment, signing, upstream data collection, betting or
permission mutation. GitHub API checks are self-reported platform observations;
account type alone cannot independently prove a human's identity. Fail closed.
"""
import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO = "CHANCHUNWA1989/football-king-report"
PREFIX = f"/repos/{REPO}"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
APP_ID = 15368
COMMON = frozenset(("safety (3.11)", "safety (3.12)", "validate", "ledger-tests"))
FINAL = COMMON | frozenset(("security-regression", "failover-regression"))
MAX_RESPONSE_BYTES = 256_000
# This is the currently observed PRE-MERGE stack. After a reviewed ancestor
# is merged, a new explicit migration manifest is required. No silent rebasing.
STAGES = (
    (429, "research/point-in-time-evidence-cut-20261104", "main"),
    (430, "research/live-event-consensus-vnext-20261104",
     "research/point-in-time-evidence-cut-20261104"),
    (431, "research/vnext-unified-score-markets-20261104",
     "research/live-event-consensus-vnext-20261104"),
    (433, "research/vnext-dynamic-dc-challenger-20261104",
     "research/vnext-unified-score-markets-20261104"),
    (434, "research/vnext-shadow-forward-evidence-20261104",
     "research/vnext-dynamic-dc-challenger-20261104"),
    (435, "research/vnext-prospective-witness-oos-20261104",
     "research/vnext-shadow-forward-evidence-20261104"),
    (436, "research/vnext-attested-forecast-evidence-pr07-20261104",
     "research/vnext-prospective-witness-oos-20261104"),
    (437, "research/vnext-pr08-controlled-signer-canary-20261104",
     "research/vnext-attested-forecast-evidence-pr07-20261104"),
    (438, "research/vnext-pr09-signer-governance-gate-20261104",
     "research/vnext-pr08-controlled-signer-canary-20261104"),
    (440, "research/vnext-pr10-unique-ci-check-identities-20261104",
     "research/vnext-pr09-signer-governance-gate-20261104"),
)


def _hex(value):
    return type(value) is str and SHA40.fullmatch(value) is not None


def _append(blockers, code, number=None):
    item = {"code": code}
    if number is not None:
        item["pr"] = number
    if item not in blockers:
        blockers.append(item)


def _protection_errors(protection, blockers):
    if type(protection) is not dict:
        _append(blockers, "PROTECTION_POLICY_NOT_VERIFIABLE")
        return
    review = protection.get("required_pull_request_reviews")
    if (type(review) is not dict
            or type(review.get("required_approving_review_count")) is not int
            or review["required_approving_review_count"] < 1
            or review.get("dismiss_stale_reviews") is not True
            or review.get("require_last_push_approval") is not True):
        _append(blockers, "INDEPENDENT_FRESH_REVIEWS_NOT_ENFORCED")
    admins = protection.get("enforce_admins")
    if type(admins) is not dict or admins.get("enabled") is not True:
        _append(blockers, "ADMIN_BYPASS_NOT_BLOCKED")
    status = protection.get("required_status_checks")
    if type(status) is not dict or status.get("strict") is not True:
        _append(blockers, "STRICT_REQUIRED_CI_NOT_ENFORCED")
    else:
        checks = status.get("checks")
        if type(checks) is not list or len(checks) == 0:
            _append(blockers, "REQUIRED_CI_APP_NOT_PINNED")
        else:
            found = {}
            for item in checks:
                if (type(item) is not dict
                        or type(item.get("context")) is not str
                        or type(item.get("app_id")) is not int
                        or item["context"] in found):
                    _append(blockers, "AMBIGUOUS_REQUIRED_CI_POLICY")
                    continue
                found[item["context"]] = item["app_id"]
            if any(found.get(name) != APP_ID for name in FINAL):
                _append(blockers, "SIX_MANDATORY_CI_CHECKS_NOT_APP_PINNED")
    for key, code in (
        ("allow_force_pushes", "FORCE_PUSH_PROTECTION_UNVERIFIED"),
        ("allow_deletions", "BRANCH_DELETE_PROTECTION_UNVERIFIED"),
    ):
        value = protection.get(key)
        if type(value) is not dict or value.get("enabled") is not False:
            _append(blockers, code)


def _independent_review(pr, reviews, headsha):
    if type(reviews) is not list or len(reviews) >= 100:
        return False
    owner = pr.get("user")
    author = owner.get("login") if type(owner) is dict else None
    if type(author) is not str or not author:
        return False
    latest = {}
    for rev in reviews:
        if type(rev) is not dict:
            return False
        user = rev.get("user")
        if (type(user) is not dict or type(user.get("login")) is not str
                or type(rev.get("submitted_at")) is not str
                or not rev["submitted_at"]):
            return False
        login = user["login"]
        if login == author or user.get("type") != "User":
            continue
        key = (rev["submitted_at"], rev.get("id", 0))
        if login not in latest or key > latest[login][0]:
            latest[login] = (key, rev)
    # A different GitHub account approving the exact HEAD is necessary, not
    # sufficient proof of a genuinely independent human review.
    return any(rev.get("state") == "APPROVED"
               and rev.get("commit_id") == headsha
               for _, rev in latest.values())


def _checks_ok(result, sha, required):
    if type(result) is not dict:
        return False
    rows = result.get("check_runs")
    count = result.get("total_count")
    if (type(rows) is not list or type(count) is not int
            or count != len(rows) or count >= 100):
        return False
    matching = {}
    for row in rows:
        if type(row) is not dict or row.get("name") not in required:
            continue
        app = row.get("app")
        name = row["name"]
        if name in matching:
            return False  # never accept duplicate mandatory check identity
        matching[name] = (
            row.get("head_sha") == sha
            and row.get("status") == "completed"
            and row.get("conclusion") == "success"
            and type(app) is dict and app.get("id") == APP_ID
        )
    return set(matching) == set(required) and all(matching.values())


def inspect_premerge_stack(fetch_json):
    """Observe all required GitHub endpoints. Any missing evidence => HOLD."""
    blockers = []
    observed = []
    branch_path = PREFIX + "/branches/main"
    policy_path = branch_path + "/protection"
    try:
        branch = fetch_json(branch_path)
        if type(branch) is not dict or branch.get("protected") is not True:
            _append(blockers, "MAIN_NOT_PROTECTED")
    except Exception:
        _append(blockers, "MAIN_PROTECTION_STATUS_UNAVAILABLE")
    try:
        _protection_errors(fetch_json(policy_path), blockers)
    except Exception:
        _append(blockers, "DETAILED_PROTECTION_API_UNAVAILABLE")

    for number, headbranch, basebranch in STAGES:
        path = PREFIX + f"/pulls/{number}"
        try:
            pr = fetch_json(path)
        except Exception:
            _append(blockers, "PR_METADATA_UNAVAILABLE", number)
            continue
        if type(pr) is not dict:
            _append(blockers, "INVALID_PR_METADATA", number)
            continue
        head = pr.get("head")
        base = pr.get("base")
        sha = head.get("sha") if type(head) is dict else None
        valid = (type(head) is dict and type(base) is dict
                 and head.get("ref") == headbranch
                 and base.get("ref") == basebranch
                 and type(head.get("repo")) is dict
                 and head["repo"].get("full_name") == REPO
                 and type(base.get("repo")) is dict
                 and base["repo"].get("full_name") == REPO
                 and _hex(sha) and pr.get("number") == number)
        if not valid:
            _append(blockers, "PR_STACK_BASE_OR_HEAD_MISMATCH", number)
            continue
        observed.append({"pr": number, "head_sha": sha,
                         "state": pr.get("state"), "draft": pr.get("draft")})
        if pr.get("state") != "open" or pr.get("merged_at") is not None:
            _append(blockers, "PR_NOT_OPEN_PREMERGE", number)
        if pr.get("draft") is not False:
            _append(blockers, "PR_DRAFT_NOT_REVIEW_READY", number)

        try:
            reviews = fetch_json(path + "/reviews?per_page=100")
            if not _independent_review(pr, reviews, sha):
                _append(blockers, "EXACT_HEAD_INDEPENDENT_APPROVAL_MISSING", number)
        except Exception:
            _append(blockers, "PR_REVIEWS_UNAVAILABLE", number)

        try:
            check_path = PREFIX + f"/commits/{sha}/check-runs?per_page=100"
            required = FINAL if number == 440 else COMMON
            checks = fetch_json(check_path)
            if not _checks_ok(checks, sha, required):
                _append(blockers, "EXACT_HEAD_REQUIRED_CI_NOT_VERIFIED", number)
        except Exception:
            _append(blockers, "PR_CI_STATUS_UNAVAILABLE", number)

        # Detect a moved head while querying review and CI evidence.
        try:
            again = fetch_json(path)
            if (type(again) is not dict or
                    type(again.get("head")) is not dict or
                    again["head"].get("sha") != sha or
                    again.get("base", {}).get("ref") != basebranch):
                _append(blockers, "PR_HEAD_MOVED_DURING_AUDIT", number)
        except Exception:
            _append(blockers, "PR_HEAD_RECHECK_UNAVAILABLE", number)

    return {
        "schema": "vnext-pr11-premERGE-review-evidence-v1",
        "status": "HOLD" if blockers else "RESEARCH_REVIEW_CHECKS_OBSERVED_ONLY",
        "expected_stack_count": len(STAGES),
        "observed": observed,
        "blockers": blockers,
        "github_human_identity_independently_established": False,
        "independent_security_review_verified": False,
        "permission_to_merge": False,
        "external_signature_verified": False,
        "real_data_licence_verified": False,
        "model_accuracy_improvement_verified": False,
        "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
    }


def github_reader(token):
    if type(token) is not str or not token.strip():
        raise ValueError("READ_ONLY_GITHUB_TOKEN_UNAVAILABLE")
    allow_prefix = PREFIX + "/"
    def read(path):
        if (type(path) is not str or not path.startswith(allow_prefix)
                or "?" in path and not path.endswith("?per_page=100")):
            raise ValueError("UNAUTHORIZED_GITHUB_API_PATH")
        request = Request(
            "https://api.github.com" + path,
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "football-king-pr11-readonly-stack-audit",
            },
            method="GET")
        try:
            with urlopen(request, timeout=12) as response:
                data = response.read(MAX_RESPONSE_BYTES + 1)
            if not data or len(data) > MAX_RESPONSE_BYTES:
                raise ValueError("INVALID_GITHUB_API_RESPONSE_SIZE")
            return json.loads(data)
        except (HTTPError, URLError, OSError, ValueError, UnicodeError) as exc:
            raise ValueError("GITHUB_API_READ_DENIED_OR_UNAVAILABLE") from exc
    return read


def main():
    try:
        result = inspect_premerge_stack(github_reader(os.environ.get("GH_TOKEN", "")))
    except Exception:
        result = {
            "status": "HOLD",
            "blockers": [{"code": "AUDIT_RUNTIME_ERROR"}],
            "permission_to_merge": False,
            "production_recommendations": "DISABLED",
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    # Never return a success exit code: even a complete research inventory
    # is not independent human approval or a deployment authorization.
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
