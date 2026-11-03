"""Read-only, fail-closed V5 admission audit for Control Tower PR #405.

Never merges PRs, publishes Pages, contacts market vendors or enables live trading.
A positive preflight is not a deployment authorization.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO = "CHANCHUNWA1989/football-king-report"
TARGET_PR = 405
HEAD_RE = re.compile(r"^[a-fA-F0-9]{40}$")
LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37})$")
REQUIRED_CHECKS = Counter({
    "observe": 1, "validate": 1, "stress": 1, "regression": 2,
    "safety (3.11)": 1, "safety (3.12)": 1, "ledger-tests": 1,
})
REVIEWER_PERMISSIONS = {"write", "maintain", "admin"}
MONITOR_RUN_NAME = "Football King Control Tower (read-only evidence)"
ARTIFACT_NAME = "control-tower-public-evidence"


def iso_utc(raw):
    if not isinstance(raw, str):
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value.astimezone(timezone.utc) if value.tzinfo else None


def sha(value):
    return isinstance(value, str) and HEAD_RE.fullmatch(value) is not None


def as_obj(value):
    return value if isinstance(value, dict) else {}


def same_sha(left, right):
    return sha(left) and sha(right) and left.casefold() == right.casefold()


def validate_evidence(evidence, expected_head, now=None):
    """Conservative read-only evaluation; unverified observations never pass."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must carry UTC offset")
    now = now.astimezone(timezone.utc)
    e = as_obj(evidence)
    pr = as_obj(e.get("pr"))
    main = as_obj(e.get("main"))
    policy = as_obj(e.get("branch_protection"))
    checks = as_obj(e.get("checks"))
    monitor = as_obj(e.get("monitor_run"))
    artifact = as_obj(e.get("monitor_artifact"))
    issues = []

    pr_head = as_obj(pr.get("head")).get("sha")
    base = as_obj(pr.get("base"))
    main_sha = as_obj(main.get("commit")).get("sha")
    author = as_obj(pr.get("user")).get("login")
    if pr.get("number") != TARGET_PR or pr.get("state") != "open" or pr.get("merged_at") is not None:
        issues.append("TARGET_PR_NOT_OPEN")
    if pr.get("draft") is not False:
        issues.append("TARGET_PR_DRAFT_OR_UNKNOWN")
    if not sha(expected_head) or not same_sha(pr_head, expected_head):
        issues.append("TARGET_HEAD_UNBOUND_OR_CHANGED")
    if base.get("ref") != "main" or not same_sha(base.get("sha"), main_sha):
        issues.append("BASE_MAIN_DRIFT_OR_UNKNOWN")
    if main.get("protected") is not True:
        issues.append("MAIN_UNPROTECTED_OR_UNKNOWN")
    # A bare protected flag does not establish that review and CI are enforced.
    required_review = as_obj(policy.get("required_pull_request_reviews"))
    required_ci = as_obj(policy.get("required_status_checks"))
    if not isinstance(required_review.get("required_approving_review_count"), int) or (
        isinstance(required_review.get("required_approving_review_count"), bool)
    ) or required_review["required_approving_review_count"] < 1:
        issues.append("REQUIRED_REVIEW_BRANCH_POLICY_UNVERIFIED")
    if not isinstance(required_ci.get("contexts"), list) and not isinstance(required_ci.get("checks"), list):
        issues.append("REQUIRED_CI_BRANCH_POLICY_UNVERIFIED")

    reviews = e.get("reviews")
    permissions = as_obj(e.get("reviewer_permissions"))
    latest = {}
    if isinstance(reviews, list):
        for review in reviews:
            record = as_obj(review)
            reviewer = as_obj(record.get("user")).get("login")
            at = iso_utc(record.get("submitted_at"))
            if not isinstance(reviewer, str) or not LOGIN_RE.fullmatch(reviewer) or at is None:
                continue
            if at > now:
                continue
            key = reviewer.casefold()
            if key not in latest or at > latest[key][0]:
                latest[key] = (at, record, reviewer)
            elif at == latest[key][0]:
                # Ambiguous same-time transition cannot certify the approval.
                latest[key] = (at, {}, reviewer)
    approved = []
    for _, review, reviewer in latest.values():
        if reviewer.casefold() == str(author).casefold():
            continue
        if review.get("state") != "APPROVED" or not same_sha(review.get("commit_id"), pr_head):
            continue
        permission = as_obj(permissions.get(reviewer)).get("permission")
        if permission not in REVIEWER_PERMISSIONS:
            continue
        approved.append(reviewer)
    if not approved:
        issues.append("INDEPENDENT_AUTHORIZED_HEAD_REVIEW_MISSING")

    check_items = checks.get("check_runs")
    check_count = checks.get("total_count")
    valid_checklist = isinstance(check_items, list) and (
        isinstance(check_count, int) and not isinstance(check_count, bool)
    ) and check_count == len(check_items) and len(check_items) > 0
    if valid_checklist:
        names = Counter()
        for c in check_items:
            item = as_obj(c)
            if not same_sha(item.get("head_sha"), pr_head):
                valid_checklist = False
            if item.get("status") != "completed" or item.get("conclusion") != "success":
                valid_checklist = False
            if not isinstance(item.get("name"), str):
                valid_checklist = False
            else:
                names[item["name"]] += 1
        if any(names.get(name, 0) < count for name, count in REQUIRED_CHECKS.items()):
            valid_checklist = False
    if not valid_checklist:
        issues.append("EXACT_HEAD_REQUIRED_CI_INCOMPLETE_OR_FAILED")

    monitor_ok = (
        monitor.get("name") == MONITOR_RUN_NAME and
        monitor.get("event") == "pull_request" and
        same_sha(monitor.get("head_sha"), pr_head) and
        monitor.get("status") == "completed" and
        monitor.get("conclusion") == "success" and
        isinstance(monitor.get("id"), int) and not isinstance(monitor.get("id"), bool)
    )
    artifact_run = as_obj(artifact.get("workflow_run"))
    artifact_ok = (
        monitor_ok and artifact.get("name") == ARTIFACT_NAME and
        artifact.get("expired") is False and
        isinstance(artifact.get("size_in_bytes"), int) and
        not isinstance(artifact.get("size_in_bytes"), bool) and
        artifact.get("size_in_bytes") > 0 and
        artifact_run.get("id") == monitor.get("id") and
        same_sha(artifact_run.get("head_sha"), pr_head) and
        (iso_utc(artifact.get("expires_at")) or now) > now and
        isinstance(artifact.get("digest"), str) and
        re.fullmatch(r"sha256:[a-fA-F0-9]{64}", artifact["digest"]) is not None
    )
    if not artifact_ok:
        issues.append("EXACT_HEAD_MONITOR_ARTIFACT_UNVERIFIED")
    # Even full metadata cannot authenticate artifact bytes or third-party provenance.
    return {
        "schema": "football-king-control-tower-release-preflight-v1",
        "generated_at_utc": now.isoformat(),
        "target_pr": TARGET_PR,
        "expected_head_sha": expected_head if sha(expected_head) else None,
        "observed_head_sha": pr_head if sha(pr_head) else None,
        "main_sha": main_sha if sha(main_sha) else None,
        "approved_reviewer_logins": approved,
        "evidence": {
            "main_protected": main.get("protected") if isinstance(main.get("protected"), bool) else None,
            "observed_exact_head_checks": len(check_items) if isinstance(check_items, list) else 0,
            "monitor_artifact_metadata_observed": bool(artifact_ok),
            "human_reviewer_permission_verified": bool(approved),
        },
        "preflight": "HOLD" if issues else "PRELIMINARY_ACCEPT_REQUIRES_MANUAL_RELEASE",
        "blockers": sorted(set(issues)),
        "release_authorized": False,
        "deployment_allowed": False,
        "production_gate": {
            "status": "HOLD",
            "production_recommendations": "DISABLED",
            "verified_positive_ev": False,
            "live_execution_allowed": False,
        },
        "limitations": [
            "This is a read-only evidence and admission report, never approval to merge.",
            "Review identity and permissions are GitHub claims, not independent proof of a human being.",
            "GitHub artifact metadata is not independent authentication of artifact contents.",
            "Post-deployment readback, monitoring schedule activation and real model accuracy are not validated.",
        ],
    }


def api(path, token):
    """Permit only paths assembled by this module, never arbitrary URLs."""
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "football-king-release-preflight-v1"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request("https://api.github.com/repos/" + REPO + "/" + path, headers=headers)
    try:
        with urlopen(request, timeout=12) as result:
            payload = result.read(2_000_001)
        if len(payload) > 2_000_000:
            return None
        return json.loads(payload)
    except (HTTPError, URLError, OSError, ValueError, UnicodeError):
        return None


def collect(expected_head, token=None):
    """All endpoints are fixed or derived from strictly verified GitHub IDs."""
    e = {
        "pr": api("pulls/405", token),
        "main": api("branches/main", token),
        "branch_protection": api("branches/main/protection", token),
        "reviews": api("pulls/405/reviews?per_page=100", token),
    }
    if not sha(expected_head):
        return e
    e["checks"] = api("commits/" + expected_head + "/check-runs?per_page=100", token)
    response = as_obj(api(
        "actions/runs?head_sha=" + expected_head + "&event=pull_request&per_page=100",
        token,
    ))
    candidates = response.get("workflow_runs")
    if isinstance(candidates, list):
        good = [r for r in candidates if isinstance(r, dict)
                and r.get("name") == MONITOR_RUN_NAME
                and r.get("event") == "pull_request"
                and same_sha(r.get("head_sha"), expected_head)]
        if good:
            good.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
            e["monitor_run"] = good[0]
            rid = good[0].get("id")
            if isinstance(rid, int) and not isinstance(rid, bool) and 0 < rid < 10**16:
                artifacts = as_obj(api("actions/runs/" + str(rid) + "/artifacts?per_page=100", token))
                items = artifacts.get("artifacts")
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict) and item.get("name") == ARTIFACT_NAME:
                            e["monitor_artifact"] = item
                            break
    perm = {}
    reviews = e.get("reviews")
    if isinstance(reviews, list):
        for reviewer in reviews[:20]:
            name = as_obj(as_obj(reviewer).get("user")).get("login")
            if isinstance(name, str) and LOGIN_RE.fullmatch(name) and name not in perm:
                perm[name] = api("collaborators/" + name + "/permission", token)
    e["reviewer_permissions"] = perm
    return e


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output", default="control-tower-release-preflight.json")
    parser.add_argument("--offline", action="store_true",
                        help="Use empty evidence and fail closed; do not call network")
    args = parser.parse_args()
    evidence = {} if args.offline else collect(args.expected_head, os.getenv("GITHUB_TOKEN"))
    result = validate_evidence(evidence, args.expected_head)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("preflight=" + result["preflight"])
    print("blockers=" + ",".join(result["blockers"]))
    print("release_authorized=false; deployment_allowed=false; production_gate=HOLD")


if __name__ == "__main__":
    main()
