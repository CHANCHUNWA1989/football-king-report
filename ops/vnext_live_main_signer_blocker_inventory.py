"""Live *read-only* main signing-release blocker inventory for PR #458.

This does NOT replace the stricter protected-main governance proof from
Draft PR #438 (ops/vnext_pr09_signer_preflight.py). It never authorizes
signing, source collection, model promotion, releases or betting.

Only fixed GitHub API endpoints are requested, using GITHUB_TOKEN with
read-only Actions permissions. Any denied protection detail is a blocker,
not evidence that controls are configured. Output contains no raw HTTP data.
"""
import argparse
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO = "CHANCHUNWA1989/football-king-report"
BASE = "/repos/" + REPO
BRANCH = BASE + "/branches/main"
PROTECTION = BRANCH + "/protection"
RULESETS = BASE + "/rulesets"
SIGNER = BASE + "/contents/.github/workflows/football-king-a-same-get-provenance.yml?ref=main"
PR = BASE + "/pulls/458"
REVIEWS = PR + "/reviews?per_page=100"
ENDPOINTS = (BRANCH, PROTECTION, RULESETS, SIGNER, PR, REVIEWS)
SCHEMA = "football-king-actual-main-signer-release-blockers-v1"
MAX_RESPONSE = 192_000


def _hold(*, blockers, observed, details):
    return {
        "schema": SCHEMA,
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "live_github_api_observed": observed,
        "blockers": sorted(set(blockers)),
        "observations": details,
        "signer_authorized": False,
        "attested_original_a_and_source": False,
        "source_rights_independently_approved": False,
        "independent_github_protection_configuration_verified": False,
        "certified_prospective_samples": 0,
        "positive_ev_verified": False,
        "model_promoted": False,
        "note": "Read-only GitHub API observations are NOT independent signer approval, proof of data rights, signed source bytes or prediction skill.",
    }


def _row(results, path):
    value = results.get(path)
    if type(value) is not dict or set(value) != {"status", "data"}:
        raise ValueError("MISSING_OR_INVALID_GITHUB_API_RESPONSE")
    status, data = value["status"], value["data"]
    if type(status) is not int or status not in (200, 403, 404):
        raise ValueError("INVALID_API_RESPONSE_STATUS")
    if status == 200 and type(data) not in (dict, list):
        raise ValueError("INVALID_API_RESPONSE_SHAPE")
    if status != 200 and data is not None:
        raise ValueError("UNEXPECTED_INACCESSIBLE_API_BODY")
    return status, data


def assess(results):
    """Pure check over direct API reads, NEVER grant signing rights."""
    if type(results) is not dict or set(results) != set(ENDPOINTS):
        return _hold(blockers=["INCOMPLETE_LIVE_GITHUB_API_READS"],
                     observed=False, details={})
    try:
        branch_status, branch = _row(results, BRANCH)
        prot_status, prot = _row(results, PROTECTION)
        rules_status, rules = _row(results, RULESETS)
        signer_status, signer = _row(results, SIGNER)
        pr_status, pr = _row(results, PR)
        reviews_status, reviews = _row(results, REVIEWS)
        essential = branch_status == 200 and pr_status == 200
        if essential:
            if (branch.get("name") != "main"
                    or type(branch.get("commit")) is not dict
                    or re.fullmatch("[0-9a-f]{40}", str(branch["commit"].get("sha"))) is None
                    or type(branch.get("protected")) is not bool):
                raise ValueError("INVALID_CURRENT_MAIN_BRANCH")
            head = pr.get("head")
            base = pr.get("base")
            author = pr.get("user")
            if (type(head) is not dict or
                    re.fullmatch("[0-9a-f]{40}", str(head.get("sha"))) is None
                    or type(base) is not dict or base.get("ref") != "main"
                    or type(author) is not dict
                    or type(author.get("login")) is not str
                    or pr.get("number") != 458
                    or type(pr.get("draft")) is not bool):
                raise ValueError("INVALID_CURRENT_PR_METADATA")
        blockers = []
        observations = {}
        if branch_status != 200:
            blockers.append("MAIN_BRANCH_METADATA_NOT_READABLE")
        else:
            observations["main_sha"] = branch["commit"]["sha"]
            observations["main_protected_flag"] = branch["protected"]
            if branch["protected"] is not True:
                blockers.append("MAIN_NOT_PROTECTED")
        if prot_status != 200:
            blockers.append("DETAILED_PROTECTION_NOT_READABLE_OR_CONFIGURED")
            observations["detailed_protection_response"] = prot_status
        else:
            count = prot.get("required_pull_request_reviews")
            status = prot.get("required_status_checks")
            enforce = prot.get("enforce_admins")
            force = prot.get("allow_force_pushes")
            delete = prot.get("allow_deletions")
            if (type(count) is not dict or
                    type(count.get("required_approving_review_count")) is not int or
                    count["required_approving_review_count"] < 1 or
                    count.get("dismiss_stale_reviews") is not True or
                    count.get("require_last_push_approval") is not True or
                    type(status) is not dict or status.get("strict") is not True or
                    type(status.get("checks")) is not list or
                    not status["checks"] or
                    type(enforce) is not dict or enforce.get("enabled") is not True or
                    type(force) is not dict or force.get("enabled") is not False or
                    type(delete) is not dict or delete.get("enabled") is not False):
                blockers.append("BRANCH_PROTECTION_NOT_FULLY_ENFORCED")
            observations["protection_details_readable"] = True
        if rules_status != 200:
            blockers.append("RULESETS_NOT_READABLE")
            observations["rulesets_response"] = rules_status
        else:
            observations["rulesets_count"] = len(rules)
            # Rulesets are supplementary; branch protection details (above)
            # must still be independently checkable by an admin.
        if signer_status != 200:
            blockers.append("APPROVED_MAIN_SIGNER_WORKFLOW_NOT_PRESENT")
            observations["signer_file_response"] = signer_status
        else:
            if (type(signer) is not dict or
                    signer.get("type") != "file" or
                    signer.get("path") !=
                    ".github/workflows/football-king-a-same-get-provenance.yml"
                    or re.fullmatch("[0-9a-f]{40}", str(signer.get("sha"))) is None):
                raise ValueError("INVALID_MAIN_SIGNER_FILE")
            observations["main_signer_workflow_exists"] = True
        if pr_status != 200:
            blockers.append("PR_458_METADATA_NOT_READABLE")
        else:
            observations["pr_458_head_sha"] = pr["head"]["sha"]
            observations["pr_458_draft"] = pr["draft"]
            observations["pr_458_state"] = pr.get("state")
            if pr["draft"] is True or pr.get("state") != "open":
                blockers.append("PR_458_NOT_READY_FOR_INDEPENDENT_REVIEW")
        if reviews_status != 200:
            blockers.append("PR_458_REVIEWS_NOT_READABLE")
        elif pr_status == 200:
            # Even an apparent approval is only an observation. The actual
            # enforced review/ruleset policy from PR #438 is a separate gate.
            if len(reviews) == 100:
                blockers.append("REVIEW_PAGINATION_NOT_COMPLETE")
            candidates = [
                r for r in reviews
                if type(r) is dict and r.get("state") == "APPROVED"
                and r.get("commit_id") == pr["head"]["sha"]
                and type(r.get("user")) is dict
                and type(r["user"].get("login")) is str
                and r["user"]["login"] != pr["user"]["login"]
                and not r["user"]["login"].endswith("[bot]")
            ]
            observations["current_head_distinct_review_candidates"] = len({
                r["user"]["login"] for r in candidates
            })
            if not candidates:
                blockers.append("NO_INDEPENDENT_CURRENT_HEAD_APPROVAL")
        if not essential:
            blockers.append("CORE_REPOSITORY_STATE_UNKNOWN")
        # Stronger policy from PR #438 and legal-source review still required
        # even if all visible API responses are apparently favorable.
        blockers.append("PR_438_GOVERNANCE_AND_INDEPENDENT_SOURCE_RIGHTS_REQUIRED")
        return _hold(blockers=blockers, observed=essential, details=observations)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return _hold(blockers=["INVALID_LIVE_GITHUB_API_DATA"],
                     observed=False, details={})


def github_read(token):
    """Single hard-coded host; no caller-provided URL, repo or trust override."""
    if type(token) is not str or not token:
        raise ValueError("GITHUB_READ_ONLY_TOKEN_REQUIRED")
    results = {}
    for path in ENDPOINTS:
        request = Request(
            "https://api.github.com" + path,
            method="GET",
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "football-king-live-main-signer-blocker-readonly",
            })
        try:
            with urlopen(request, timeout=12) as response:
                data = response.read(MAX_RESPONSE + 1)
                if not 0 < len(data) <= MAX_RESPONSE:
                    raise ValueError("GITHUB_API_RESPONSE_SIZE")
                results[path] = {"status": 200, "data": json.loads(data)}
        except HTTPError as exc:
            if exc.code in (403, 404):
                results[path] = {"status": exc.code, "data": None}
            else:
                raise ValueError("GITHUB_API_RESPONSE_UNAVAILABLE") from exc
        except (URLError, OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("GITHUB_API_RESPONSE_UNAVAILABLE") from exc
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    args = parser.parse_args(argv)
    try:
        report = assess(github_read(os.getenv("GH_TOKEN", "")))
    except (ValueError, OSError, TypeError) as exc:
        report = _hold(blockers=[str(exc) if type(exc) is ValueError
                                 else "GITHUB_READ_ONLY_API_FAILURE"],
                       observed=False, details={})
    print(json.dumps(report, sort_keys=True))
    # Successful execution means actual essential API reads completed and
    # the report remains BLOCKED. It NEVER permits signing or merging.
    return 0 if report["live_github_api_observed"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
