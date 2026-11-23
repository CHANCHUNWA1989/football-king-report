"""Advisory, fail-closed independent-review readiness check for Agent Reach PRs.

This is NOT a replacement for a protected branch / repository ruleset.
A workflow run evaluating code from the PR head is not a trusted required
check until a repository administrator configures enforcement on main.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SHA = re.compile(r"[a-f0-9]{40}\Z")
ALLOWED_ASSOCIATION = {"COLLABORATOR", "MEMBER", "OWNER"}
STATES = {"APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED", "PENDING"}


class ReviewHold(ValueError):
    """Missing, stale, self-authored or otherwise unaudited review."""


def _login(value: object) -> str:
    if not isinstance(value, dict) or not isinstance(value.get("login"), str):
        raise ReviewHold("INVALID_REVIEW_IDENTITY")
    name = value["login"]
    if not name or len(name) > 100 or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-" for ch in name):
        raise ReviewHold("INVALID_REVIEW_IDENTITY")
    return name


def assert_fresh_pr_snapshot(
    before: object, after: object, event_head_sha: str, event_pr_number: int
) -> str:
    """Reject a PR head/base/identity change during the GitHub review read.

    An event SHA is required: neither the first nor the second API response
    is trusted to define the triggering revision on its own. This is only a
    TOCTOU mitigation; a post-check push can still happen on GitHub.
    """
    if not isinstance(event_head_sha, str) or not SHA.fullmatch(event_head_sha):
        raise ReviewHold("INVALID_EVENT_HEAD")
    if type(event_pr_number) is not int or not 1 <= event_pr_number <= 999999999:
        raise ReviewHold("INVALID_EVENT_PR_NUMBER")

    def identity(record: object) -> tuple:
        if not isinstance(record, dict):
            raise ReviewHold("INVALID_PR_SNAPSHOT")
        number = record.get("number")
        if type(number) is not int or number < 1:
            raise ReviewHold("INVALID_PR_NUMBER")
        author = _login(record.get("user")).lower()
        head = record.get("head")
        base = record.get("base")
        head_sha = head.get("sha") if isinstance(head, dict) else None
        base_ref = base.get("ref") if isinstance(base, dict) else None
        if (not isinstance(head_sha, str) or not SHA.fullmatch(head_sha) or
                not isinstance(base_ref, str) or not 1 <= len(base_ref) <= 200 or
                any(x in base_ref for x in (" ", "\t", "\r", "\n", "..", "\\"))):
            raise ReviewHold("INVALID_PR_REF")
        if (record.get("state") != "open" or record.get("draft") is not False or
                record.get("merged") is not False):
            raise ReviewHold("PR_NOT_READY_FOR_INDEPENDENT_REVIEW")
        return (number, author, head_sha, base_ref)

    original = identity(before)
    fresh = identity(after)
    if (original != fresh or original[0] != event_pr_number or
            original[2] != event_head_sha):
        raise ReviewHold("STALE_OR_MISMATCHED_PR_SNAPSHOT")
    return event_head_sha


def evaluate(pr: object, reviews: object, *, permissions: object = None) -> dict:
    """Only observe a human approval when CURRENT repository write access is verified.

    GitHub author_association is not permission. Caller must provide the
    read-only REST /collaborators/{login}/permission response for each candidate.
    Missing/403/malformed evidence never promotes an approval.
    """
    # Missing permission input is equivalent to zero verified permissions,
    # never to approval; keep distinct HOLD reasons for zero reviews and
    # outstanding CHANGES_REQUESTED evidence.
    if permissions is None:
        permissions = {}
    if (not isinstance(pr, dict) or not isinstance(reviews, list) or
            len(reviews) > 100 or not isinstance(permissions, dict) or
            len(permissions) > 10):
        raise ReviewHold("INVALID_PR_OR_REVIEW_PERMISSION_EVIDENCE")
    author = _login(pr.get("user"))
    head = pr.get("head")
    sha = head.get("sha") if isinstance(head, dict) else None
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise ReviewHold("INVALID_HEAD_SHA")
    if pr.get("state") != "open" or pr.get("draft") is not False or pr.get("merged") is not False:
        raise ReviewHold("PR_NOT_READY_FOR_INDEPENDENT_REVIEW")

    latest = {}
    for review in reviews:
        if not isinstance(review, dict):
            raise ReviewHold("INVALID_REVIEW")
        reviewer = review.get("user")
        name = _login(reviewer)
        state = review.get("state")
        if state not in STATES:
            raise ReviewHold("UNKNOWN_REVIEW_STATE")
        if state == "PENDING":
            continue  # Unsubmitted reviews never authorize a release.
        if not isinstance(review.get("id"), int) or review["id"] < 1:
            raise ReviewHold("INVALID_REVIEW_ID")
        if not isinstance(review.get("submitted_at"), str) or not review["submitted_at"]:
            raise ReviewHold("INVALID_REVIEW_TIMESTAMP")
        # GitHub review REST ids are unique and monotonically increasing.
        # Sort instead of trusting API response order.
        old = latest.get(name.lower())
        if old is None or review["id"] > old["id"]:
            latest[name.lower()] = review

    valid_approval = False
    observed_approval = False
    for name, review in latest.items():
        state = review["state"]
        if name == author.lower():
            continue
        if state == "CHANGES_REQUESTED":
            raise ReviewHold("OUTSTANDING_NON_AUTHOR_CHANGES_REQUEST")
        if state != "APPROVED":
            continue
        identity = review["user"]
        if identity.get("type") != "User" or name.endswith("-bot") or name.endswith("[bot]"):
            continue
        if review.get("author_association") not in ALLOWED_ASSOCIATION:
            continue
        # GitHub review.commit_id is what was actually reviewed. Anything
        # older than the PR head is stale, even if GitHub leaves it visible.
        if review.get("commit_id") != sha:
            continue
        observed_approval = True
        permission = permissions.get(name)
        if not isinstance(permission, dict):
            continue
        # Do not infer current permissions from author_association, user
        # type, submitted_at, or an unauthenticated review-body claim.
        if (not isinstance(permission.get("login"), str) or
                permission["login"].lower() != name or
                permission.get("permission") not in ("write", "maintain", "admin")):
            continue
        valid_approval = True
    if not valid_approval:
        if observed_approval:
            raise ReviewHold("REVIEWER_WRITE_PERMISSION_UNVERIFIED")
        raise ReviewHold("INDEPENDENT_CURRENT_HEAD_APPROVAL_MISSING")
    return {
        "schema": "agent-reach-advisory-independent-review-v1",
        "review_evidence_present": True,
        "head_sha": sha,
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "eligible_for_model": False,
        "verified_positive_ev": None,
        "github_branch_protection_verified": False,
        "reviewer_write_permission_verified": True,
        "independent_review_readiness": "OBSERVED_NOT_AUTHORIZED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--permissions", type=Path, required=True)
    parser.add_argument("--post-pr", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-pr-number", type=int, required=True)
    args = parser.parse_args()
    try:
        if (any(p.is_symlink() or not p.is_file() for p in
                (args.pr, args.reviews, args.post_pr, args.permissions)) or
                args.pr.stat().st_size > 250_000 or
                args.post_pr.stat().st_size > 250_000 or
                args.reviews.stat().st_size > 1_000_000 or
                args.permissions.stat().st_size > 50_000):
            raise ReviewHold("UNSAFE_EVIDENCE_FILES")
        pr = json.loads(args.pr.read_text(encoding="utf-8"))
        reviews = json.loads(args.reviews.read_text(encoding="utf-8"))
        permissions = json.loads(args.permissions.read_text(encoding="utf-8"))
        post_pr = json.loads(args.post_pr.read_text(encoding="utf-8"))
        assert_fresh_pr_snapshot(pr, post_pr, args.expected_head, args.expected_pr_number)
        report = evaluate(pr, reviews, permissions=permissions)
    except (ReviewHold, ValueError, TypeError, OSError, UnicodeError) as exc:
        code = str(exc) if isinstance(exc, ReviewHold) else "INVALID_EVIDENCE"
        if code not in {
            "INDEPENDENT_CURRENT_HEAD_APPROVAL_MISSING",
            "REVIEWER_WRITE_PERMISSION_UNVERIFIED",
            "OUTSTANDING_NON_AUTHOR_CHANGES_REQUEST",
            "PR_NOT_READY_FOR_INDEPENDENT_REVIEW",
            "STALE_OR_MISMATCHED_PR_SNAPSHOT",
        }:
            code = "INVALID_EVIDENCE"
        print(f"REVIEW_GATE_HOLD reason={code}; production_recommendations=DISABLED")
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
