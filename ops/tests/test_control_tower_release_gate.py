"""V5 offline release gate regression suite: no real market, reviewer or vendor data."""
import copy
from datetime import datetime, timedelta, timezone
import unittest

from ops.control_tower_release_gate import (
    validate_evidence, collect, iso_utc, TARGET_PR
)

NOW = datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)
HEAD = "a" * 40
MAIN = "b" * 40

CHECK_NAMES = [
    "observe", "validate", "stress", "regression", "regression",
    "safety (3.11)", "safety (3.12)", "ledger-tests",
]


def good():
    return {
        "pr": {
            "number": TARGET_PR, "state": "open", "draft": False,
            "merged_at": None, "user": {"login": "author"},
            "head": {"sha": HEAD}, "base": {"ref": "main", "sha": MAIN},
        },
        "main": {"protected": True, "commit": {"sha": MAIN}},
        "branch_protection": {
            "required_pull_request_reviews": {"required_approving_review_count": 1},
            "required_status_checks": {
                "strict": True, "contexts": CHECK_NAMES,
            },
        },
        "reviews": [{
            "user": {"login": "reviewer-a"}, "state": "APPROVED",
            "commit_id": HEAD, "submitted_at": "2026-11-03T14:59:00Z",
        }],
        "reviewer_permissions": {"reviewer-a": {"permission": "write"}},
        "checks": {
            "total_count": 8,
            "check_runs": [
                {"name": name, "status": "completed", "conclusion": "success",
                 "head_sha": HEAD} for name in CHECK_NAMES
            ],
        },
        "monitor_run": {
            "id": 1001, "name": "Football King Control Tower (read-only evidence)",
            "event": "pull_request", "head_sha": HEAD,
            "status": "completed", "conclusion": "success",
        },
        "monitor_artifact": {
            "name": "control-tower-public-evidence",
            "expired": False,
            "size_in_bytes": 1100,
            "expires_at": "2026-11-10T14:59:00Z",
            "digest": "sha256:" + ("c" * 64),
            "workflow_run": {"id": 1001, "head_sha": HEAD},
        },
    }


class ReleasePreflightTests(unittest.TestCase):
    def assess(self, evidence, expected=HEAD):
        return validate_evidence(evidence, expected, now=NOW)

    def test_synthetic_complete_is_only_preliminary_not_release_permission(self):
        state = self.assess(good())
        self.assertEqual(state["preflight"], "PRELIMINARY_ACCEPT_REQUIRES_MANUAL_RELEASE")
        self.assertEqual(state["blockers"], [])
        self.assertFalse(state["release_authorized"])
        self.assertFalse(state["deployment_allowed"])
        self.assertEqual(state["production_gate"]["status"], "HOLD")

    def test_draft_blocks(self):
        data = good()
        data["pr"]["draft"] = True
        self.assertIn("TARGET_PR_DRAFT_OR_UNKNOWN", self.assess(data)["blockers"])

    def test_changed_head_blocks(self):
        data = good()
        data["pr"]["head"]["sha"] = "f" * 40
        self.assertIn("TARGET_HEAD_UNBOUND_OR_CHANGED", self.assess(data)["blockers"])

    def test_base_main_drift_blocks(self):
        data = good()
        data["main"]["commit"]["sha"] = "e" * 40
        self.assertIn("BASE_MAIN_DRIFT_OR_UNKNOWN", self.assess(data)["blockers"])

    def test_unprotected_main_blocks(self):
        data = good()
        data["main"]["protected"] = False
        self.assertIn("MAIN_UNPROTECTED_OR_UNKNOWN", self.assess(data)["blockers"])

    def test_missing_policy_details_block(self):
        data = good()
        data["branch_protection"] = None
        blocked = self.assess(data)["blockers"]
        self.assertIn("REQUIRED_REVIEW_BRANCH_POLICY_UNVERIFIED", blocked)
        self.assertIn("REQUIRED_CI_BRANCH_POLICY_UNVERIFIED", blocked)

    def test_empty_required_ci_policy_blocks(self):
        data = good()
        data["branch_protection"]["required_status_checks"] = {"contexts": [], "checks": []}
        self.assertIn("REQUIRED_CI_BRANCH_POLICY_UNVERIFIED", self.assess(data)["blockers"])

    def test_self_approval_not_independent(self):
        data = good()
        data["reviews"][0]["user"]["login"] = "author"
        data["reviewer_permissions"]["author"] = {"permission": "admin"}
        self.assertIn("INDEPENDENT_AUTHORIZED_HEAD_REVIEW_MISSING",
                      self.assess(data)["blockers"])

    def test_approval_stale_head_blocks(self):
        data = good()
        data["reviews"][0]["commit_id"] = "c" * 40
        self.assertIn("INDEPENDENT_AUTHORIZED_HEAD_REVIEW_MISSING",
                      self.assess(data)["blockers"])

    def test_permission_unknown_blocks(self):
        data = good()
        data["reviewer_permissions"] = {}
        self.assertIn("INDEPENDENT_AUTHORIZED_HEAD_REVIEW_MISSING",
                      self.assess(data)["blockers"])

    def test_later_changes_requested_invalidates_approval(self):
        data = good()
        data["reviews"].append({
            "user": {"login": "reviewer-a"}, "state": "CHANGES_REQUESTED",
            "commit_id": HEAD, "submitted_at": "2026-11-03T14:59:30Z",
        })
        self.assertIn("INDEPENDENT_AUTHORIZED_HEAD_REVIEW_MISSING",
                      self.assess(data)["blockers"])

    def test_duplicate_review_time_cannot_certify(self):
        data = good()
        data["reviews"].append({
            "user": {"login": "reviewer-a"}, "state": "COMMENTED",
            "commit_id": HEAD, "submitted_at": "2026-11-03T14:59:00Z",
        })
        self.assertIn("INDEPENDENT_AUTHORIZED_HEAD_REVIEW_MISSING",
                      self.assess(data)["blockers"])

    def test_failed_check_blocks(self):
        data = good()
        data["checks"]["check_runs"][0]["conclusion"] = "failure"
        self.assertIn("EXACT_HEAD_REQUIRED_CI_INCOMPLETE_OR_FAILED",
                      self.assess(data)["blockers"])

    def test_partial_check_response_blocks(self):
        data = good()
        data["checks"]["total_count"] = 9
        self.assertIn("EXACT_HEAD_REQUIRED_CI_INCOMPLETE_OR_FAILED",
                      self.assess(data)["blockers"])

    def test_missing_required_check_blocks(self):
        data = good()
        data["checks"]["check_runs"][-1]["name"] = "other-check"
        self.assertIn("EXACT_HEAD_REQUIRED_CI_INCOMPLETE_OR_FAILED",
                      self.assess(data)["blockers"])

    def test_bad_artifact_lineage_blocks(self):
        data = good()
        data["monitor_artifact"]["workflow_run"]["head_sha"] = "e" * 40
        self.assertIn("EXACT_HEAD_MONITOR_ARTIFACT_UNVERIFIED",
                      self.assess(data)["blockers"])

    def test_expired_artifact_blocks(self):
        data = good()
        data["monitor_artifact"]["expires_at"] = "2026-11-01T14:59:00Z"
        self.assertIn("EXACT_HEAD_MONITOR_ARTIFACT_UNVERIFIED",
                      self.assess(data)["blockers"])

    def test_offline_missing_everything_holds(self):
        state = self.assess({})
        self.assertEqual(state["preflight"], "HOLD")
        self.assertFalse(state["release_authorized"])
        self.assertGreaterEqual(len(state["blockers"]), 5)

    def test_timezone_unknown_is_not_assumed_utc(self):
        self.assertIsNone(iso_utc("2026-11-03T14:00:00"))

    def test_future_approval_rejected(self):
        data = good()
        data["reviews"][0]["submitted_at"] = "2026-11-03T15:01:00Z"
        self.assertIn("INDEPENDENT_AUTHORIZED_HEAD_REVIEW_MISSING",
                      self.assess(data)["blockers"])


    def test_missing_required_status_context_blocks(self):
        data = good()
        data["branch_protection"]["required_status_checks"]["contexts"] = ["observe"]
        self.assertIn("REQUIRED_CI_BRANCH_POLICY_UNVERIFIED",
                      self.assess(data)["blockers"])

    def test_non_strict_branch_policy_blocks(self):
        data = good()
        data["branch_protection"]["required_status_checks"]["strict"] = False
        self.assertIn("REQUIRED_CI_BRANCH_POLICY_UNVERIFIED",
                      self.assess(data)["blockers"])

    def test_insufficient_independent_approvals_blocks(self):
        data = good()
        data["branch_protection"]["required_pull_request_reviews"]["required_approving_review_count"] = 2
        self.assertIn("INDEPENDENT_AUTHORIZED_HEAD_REVIEW_MISSING",
                      self.assess(data)["blockers"])

    def test_unpaged_review_history_cannot_establish_approval(self):
        data = good()
        # More than a single REST page could conceal a more recent rejection.
        data["reviews"] = data["reviews"] + [{
            "user": {"login": "extra-" + str(i)}, "state": "COMMENTED",
            "commit_id": HEAD, "submitted_at": "2026-11-03T14:30:00Z",
        } for i in range(99)]
        self.assertIn("REVIEW_HISTORY_PAGINATION_UNVERIFIED",
                      self.assess(data)["blockers"])



if __name__ == "__main__":
    unittest.main()
