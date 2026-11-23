"""Offline negative/positive evidence cases for advisory Agent Reach review gate."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_reach_review_guard import ReviewHold, evaluate

SHA = "a" * 40
OLD = "b" * 40
PR = {"user": {"login": "project-author", "type": "User"},
      "head": {"sha": SHA}, "state": "open", "draft": False, "merged": False}
REVIEW = {"id": 101, "user": {"login": "trusted-human", "type": "User"},
          "state": "APPROVED", "submitted_at": "2026-11-23T12:00:00Z",
          "commit_id": SHA, "author_association": "COLLABORATOR"}


class IndependentReviewGuardTests(unittest.TestCase):
    def test_current_head_independent_human_approval_only_observed_not_authorized(self):
        result = evaluate(copy.deepcopy(PR), [copy.deepcopy(REVIEW)])
        self.assertEqual(result["independent_review_readiness"], "OBSERVED_NOT_AUTHORIZED")
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["github_branch_protection_verified"])
        self.assertFalse(result["reviewer_write_permission_verified"])
        self.assertFalse(result["eligible_for_model"])
        self.assertIsNone(result["verified_positive_ev"])

    def test_missing_reviewer_fails_closed(self):
        with self.assertRaisesRegex(ReviewHold, "INDEPENDENT_CURRENT_HEAD_APPROVAL_MISSING"):
            evaluate(PR, [])

    def test_author_approval_never_counts(self):
        self_review = {**REVIEW, "user": {"login": "project-author", "type": "User"}}
        with self.assertRaises(ReviewHold):
            evaluate(PR, [self_review])

    def test_outdated_head_review_never_counts(self):
        with self.assertRaises(ReviewHold):
            evaluate(PR, [{**REVIEW, "commit_id": OLD}])

    def test_changes_requested_outweighs_approval(self):
        request = {**REVIEW, "id": 103, "state": "CHANGES_REQUESTED"}
        with self.assertRaisesRegex(ReviewHold, "OUTSTANDING_NON_AUTHOR_CHANGES_REQUEST"):
            evaluate(PR, [REVIEW, request])

    def test_most_recent_nonapproved_review_overrides_older_approval(self):
        comment = {**REVIEW, "id": 102, "state": "COMMENTED"}
        with self.assertRaises(ReviewHold):
            evaluate(PR, [comment, REVIEW])

    def test_dismissal_cancels_approval(self):
        dismissed = {**REVIEW, "id": 102, "state": "DISMISSED"}
        with self.assertRaises(ReviewHold):
            evaluate(PR, [REVIEW, dismissed])

    def test_noncollaborator_or_bot_never_counts(self):
        cases = [
            {**REVIEW, "author_association": "CONTRIBUTOR"},
            {**REVIEW, "user": {"login": "automated-bot", "type": "Bot"}},
            {**REVIEW, "user": {"login": "other", "type": "Bot"}},
            {**REVIEW, "user": {"login": "trusted-human", "type": "Organization"}},
        ]
        for item in cases:
            with self.subTest(item=item), self.assertRaises(ReviewHold):
                evaluate(PR, [item])

    def test_pending_review_does_not_count(self):
        with self.assertRaises(ReviewHold):
            evaluate(PR, [{**REVIEW, "state": "PENDING"}])

    def test_latest_review_out_of_order(self):
        comment = {**REVIEW, "id": 103, "state": "COMMENTED"}
        with self.assertRaises(ReviewHold):
            evaluate(PR, [comment, REVIEW])

    def test_unknown_state_or_bad_identity_fail_closed(self):
        for item in (
            {**REVIEW, "state": "MAGIC_APPROVAL"},
            {**REVIEW, "id": "101"},
            {**REVIEW, "user": {"login": "bad user", "type": "User"}},
            {"state": "APPROVED"},
        ):
            with self.subTest(item=item), self.assertRaises(ReviewHold):
                evaluate(PR, [item])

    def test_pr_draft_closed_or_merged_not_ready(self):
        for field, value in (("draft", True), ("state", "closed"), ("merged", True)):
            with self.subTest(field=field), self.assertRaises(ReviewHold):
                evaluate({**PR, field: value}, [REVIEW])

    def test_wrong_sha_type_never_counts(self):
        for sha in (OLD[:20], "not-a-sha", None):
            with self.subTest(sha=sha), self.assertRaises(ReviewHold):
                evaluate({**PR, "head": {"sha": sha}}, [REVIEW])

    def test_new_review_from_other_author_does_not_erase_valid_approval(self):
        other = {**REVIEW, "id": 201, "user": {"login": "another-human", "type": "User"},
                 "state": "COMMENTED"}
        self.assertTrue(evaluate(PR, [other, REVIEW])["review_evidence_present"])

    def test_json_cli_exits_nonzero_when_no_reviews(self):
        script = Path(__file__).resolve().parents[1] / "agent_reach_review_guard.py"
        with tempfile.TemporaryDirectory() as root:
            a, b = Path(root) / "pr.json", Path(root) / "reviews.json"
            a.write_text(json.dumps(PR), encoding="utf-8")
            b.write_text("[]", encoding="utf-8")
            process = subprocess.run([sys.executable, str(script), "--pr", str(a),
                                      "--reviews", str(b)],
                                     check=False, capture_output=True, text=True)
            self.assertEqual(process.returncode, 2)
            self.assertIn("INDEPENDENT_CURRENT_HEAD_APPROVAL_MISSING", process.stdout)
            self.assertNotIn("project-author", process.stdout)


if __name__ == "__main__":
    unittest.main()
