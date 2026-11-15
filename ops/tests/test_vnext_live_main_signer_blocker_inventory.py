"""Policy-only test for read-only live blocker observation.

No mocked 200 result can grant signer rights or certify an A forecast.
"""
import copy
import json
import unittest
from unittest.mock import patch

from ops.vnext_live_main_signer_blocker_inventory import (
    BRANCH, PROTECTION, RULESETS, SIGNER, PR, REVIEWS, ENDPOINTS,
    assess, github_read,
)

SHA = "a" * 40


def sample():
    protection = {
        "required_pull_request_reviews": {
            "required_approving_review_count": 1,
            "dismiss_stale_reviews": True,
            "require_last_push_approval": True,
        },
        "required_status_checks": {
            "strict": True, "checks": [{"context": "safety (3.11)", "app_id": 15368}],
        },
        "enforce_admins": {"enabled": True},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
    }
    return {
        BRANCH: {"status": 200, "data": {
            "name": "main", "protected": True, "commit": {"sha": "b" * 40}}},
        PROTECTION: {"status": 200, "data": protection},
        RULESETS: {"status": 200, "data": []},
        SIGNER: {"status": 200, "data": {
            "type": "file",
            "sha": "c" * 40,
            "path": ".github/workflows/football-king-a-same-get-provenance.yml"}},
        PR: {"status": 200, "data": {
            "number": 458, "draft": False, "state": "open",
            "head": {"sha": SHA}, "base": {"ref": "main"},
            "user": {"login": "repo-owner"}}},
        REVIEWS: {"status": 200, "data": [{
            "state": "APPROVED", "commit_id": SHA,
            "user": {"login": "independent-human"}}]},
    }


class LiveSignerInventoryTests(unittest.TestCase):
    def check(self, data=None):
        return assess(copy.deepcopy(sample() if data is None else data))

    def held(self, report):
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertFalse(report["signer_authorized"])
        self.assertFalse(report["attested_original_a_and_source"])
        self.assertFalse(report["source_rights_independently_approved"])
        self.assertFalse(report["independent_github_protection_configuration_verified"])
        self.assertFalse(report["positive_ev_verified"])
        self.assertFalse(report["model_promoted"])
        self.assertEqual(report["certified_prospective_samples"], 0)

    def test_ideal_mock_still_never_signer_authorized(self):
        r = self.check()
        self.held(r)
        self.assertTrue(r["live_github_api_observed"])
        self.assertEqual(r["observations"]["current_head_distinct_review_candidates"], 1)
        self.assertEqual(r["blockers"],
                         ["PR_438_GOVERNANCE_AND_INDEPENDENT_SOURCE_RIGHTS_REQUIRED"])

    def test_actual_unprotected_no_ruleset_no_signer_no_review_is_hold(self):
        d = sample()
        d[BRANCH]["data"]["protected"] = False
        d[PROTECTION] = {"status": 403, "data": None}
        d[SIGNER] = {"status": 404, "data": None}
        d[REVIEWS]["data"] = []
        r = self.check(d)
        self.held(r)
        for reason in ("MAIN_NOT_PROTECTED", "DETAILED_PROTECTION_NOT_READABLE_OR_CONFIGURED",
                       "APPROVED_MAIN_SIGNER_WORKFLOW_NOT_PRESENT",
                       "NO_INDEPENDENT_CURRENT_HEAD_APPROVAL"):
            self.assertIn(reason, r["blockers"])
        self.assertTrue(r["live_github_api_observed"])

    def test_missing_branch_response_fails_readiness_observation(self):
        d = sample()
        d[BRANCH] = {"status": 403, "data": None}
        r = self.check(d)
        self.held(r)
        self.assertFalse(r["live_github_api_observed"])
        self.assertIn("CORE_REPOSITORY_STATE_UNKNOWN", r["blockers"])

    def test_missing_pr_response_fails_readiness_observation(self):
        d = sample()
        d[PR] = {"status": 404, "data": None}
        r = self.check(d)
        self.held(r)
        self.assertFalse(r["live_github_api_observed"])

    def test_missing_or_extra_endpoint_rejected(self):
        d = sample()
        del d[PR]
        r = self.check(d)
        self.held(r)
        self.assertFalse(r["live_github_api_observed"])
        self.assertIn("INCOMPLETE_LIVE_GITHUB_API_READS", r["blockers"])
        d = sample()
        d["/attacker"] = {"status": 200, "data": {"protected": True}}
        self.assertFalse(self.check(d)["live_github_api_observed"])

    def test_unknown_http_status_cannot_be_used_as_api_proof(self):
        d = sample()
        d[PROTECTION] = {"status": 201, "data": None}
        r = self.check(d)
        self.held(r)
        self.assertFalse(r["live_github_api_observed"])

    def test_forbidden_response_cannot_inject_attestation_json(self):
        d = sample()
        d[SIGNER] = {"status": 404, "data": {"signed": True}}
        r = self.check(d)
        self.held(r)
        self.assertFalse(r["live_github_api_observed"])

    def test_draft_pr_still_blocked_even_with_hypothetical_approvals(self):
        d = sample()
        d[PR]["data"]["draft"] = True
        r = self.check(d)
        self.held(r)
        self.assertIn("PR_458_NOT_READY_FOR_INDEPENDENT_REVIEW", r["blockers"])

    def test_review_from_pr_author_not_independent(self):
        d = sample()
        d[REVIEWS]["data"][0]["user"]["login"] = "repo-owner"
        r = self.check(d)
        self.held(r)
        self.assertIn("NO_INDEPENDENT_CURRENT_HEAD_APPROVAL", r["blockers"])

    def test_bot_review_is_not_independent_human(self):
        d = sample()
        d[REVIEWS]["data"][0]["user"]["login"] = "bot[bot]"
        self.assertIn("NO_INDEPENDENT_CURRENT_HEAD_APPROVAL",
                      self.check(d)["blockers"])

    def test_stale_review_prior_commit_does_not_count(self):
        d = sample()
        d[REVIEWS]["data"][0]["commit_id"] = "d" * 40
        self.assertIn("NO_INDEPENDENT_CURRENT_HEAD_APPROVAL",
                      self.check(d)["blockers"])

    def test_dismissed_review_does_not_count(self):
        d = sample()
        d[REVIEWS]["data"][0]["state"] = "DISMISSED"
        self.assertIn("NO_INDEPENDENT_CURRENT_HEAD_APPROVAL",
                      self.check(d)["blockers"])

    def test_review_list_exactly_100_is_ambiguous(self):
        d = sample()
        d[REVIEWS]["data"] = d[REVIEWS]["data"] * 100
        r = self.check(d)
        self.held(r)
        self.assertIn("REVIEW_PAGINATION_NOT_COMPLETE", r["blockers"])

    def test_insufficient_required_reviews_or_admin_enforcement(self):
        for field, new in (
            ("required_pull_request_reviews", {
                "required_approving_review_count": 0,
                "dismiss_stale_reviews": True,
                "require_last_push_approval": True}),
            ("enforce_admins", {"enabled": False}),
            ("required_status_checks", {"strict": False, "checks": []}),
            ("allow_force_pushes", {"enabled": True}),
            ("allow_deletions", {"enabled": True}),
        ):
            with self.subTest(field=field):
                d = sample()
                d[PROTECTION]["data"][field] = new
                r = self.check(d)
                self.held(r)
                self.assertIn("BRANCH_PROTECTION_NOT_FULLY_ENFORCED", r["blockers"])

    def test_unreadable_protection_is_always_blocker(self):
        for code in (403, 404):
            with self.subTest(code=code):
                d = sample()
                d[PROTECTION] = {"status": code, "data": None}
                r = self.check(d)
                self.held(r)
                self.assertIn("DETAILED_PROTECTION_NOT_READABLE_OR_CONFIGURED", r["blockers"])

    def test_unreadable_rulesets_is_unknown(self):
        d = sample()
        d[RULESETS] = {"status": 403, "data": None}
        r = self.check(d)
        self.held(r)
        self.assertIn("RULESETS_NOT_READABLE", r["blockers"])

    def test_missing_signer_on_main_blocks(self):
        d = sample()
        d[SIGNER] = {"status": 404, "data": None}
        r = self.check(d)
        self.held(r)
        self.assertIn("APPROVED_MAIN_SIGNER_WORKFLOW_NOT_PRESENT", r["blockers"])

    def test_unexpected_signer_path_invalidates_api_evidence(self):
        d = sample()
        d[SIGNER]["data"]["path"] = ".github/workflows/evil.yml"
        r = self.check(d)
        self.held(r)
        self.assertFalse(r["live_github_api_observed"])

    def test_fake_branch_protected_string_rejected(self):
        d = sample()
        d[BRANCH]["data"]["protected"] = "true"
        r = self.check(d)
        self.held(r)
        self.assertFalse(r["live_github_api_observed"])

    def test_wrong_pr_number_rejected(self):
        d = sample()
        d[PR]["data"]["number"] = 460
        self.assertFalse(self.check(d)["live_github_api_observed"])

    def test_missing_read_token_rejected_without_network(self):
        with self.assertRaisesRegex(ValueError, "GITHUB_READ_ONLY_TOKEN_REQUIRED"):
            github_read("")

    def test_endpoint_allowlist_is_fixed(self):
        self.assertEqual(len(ENDPOINTS), 6)
        self.assertTrue(all(x.startswith("/repos/CHANCHUNWA1989/football-king-report/")
                            for x in ENDPOINTS))


if __name__ == "__main__":
    unittest.main()
