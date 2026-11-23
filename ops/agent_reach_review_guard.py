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


def evaluate(pr: object, reviews: object) -> dict:
    if not isinstance(pr, dict) or not isinstance(reviews, list) or len(reviews) > 100:
        raise ReviewHold("INVALID_PR_OR_REVIEW_LIST")
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
        valid_approval = True
    if not valid_approval:
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
        "reviewer_write_permission_verified": False,
        "independent_review_readiness": "OBSERVED_NOT_AUTHORIZED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    args = parser.parse_args()
    try:
        if (args.pr.is_symlink() or args.reviews.is_symlink() or
                not args.pr.is_file() or not args.reviews.is_file() or
                args.pr.stat().st_size > 250_000 or
                args.reviews.stat().st_size > 1_000_000):
            raise ReviewHold("UNSAFE_EVIDENCE_FILES")
        pr = json.loads(args.pr.read_text(encoding="utf-8"))
        reviews = json.loads(args.reviews.read_text(encoding="utf-8"))
        report = evaluate(pr, reviews)
    except (ReviewHold, ValueError, TypeError, OSError, UnicodeError) as exc:
        code = str(exc) if isinstance(exc, ReviewHold) else "INVALID_EVIDENCE"
        if code not in {
            "INDEPENDENT_CURRENT_HEAD_APPROVAL_MISSING",
            "OUTSTANDING_NON_AUTHOR_CHANGES_REQUEST",
            "PR_NOT_READY_FOR_INDEPENDENT_REVIEW",
        }:
            code = "INVALID_EVIDENCE"
        print(f"REVIEW_GATE_HOLD reason={code}; production_recommendations=DISABLED")
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
