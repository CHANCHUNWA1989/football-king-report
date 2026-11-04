"""PR-09 offline governance preflight regression and adversarial tests."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vnext_pr09_signer_preflight import (
    BRANCH_ENDPOINT, PROTECTION_ENDPOINT, GovernanceHold,
    assess_preflight, github_api_fetch,
)

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "football-king-vnext-forecast-attest.yml"
SHA = "a" * 40


def context():
    return {
        "GITHUB_REPOSITORY": "CHANCHUNWA1989/football-king-report",
        "GITHUB_REPOSITORY_ID": "1411226578",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REF_TYPE": "branch",
        "GITHUB_SHA": SHA,
        "GITHUB_RUN_ID": "123456",
        "GITHUB_RUN_ATTEMPT": "1",
    }


def responses():
    return {
        BRANCH_ENDPOINT: {"name": "main", "commit": {"sha": SHA}, "protected": True},
        PROTECTION_ENDPOINT: {
            "required_pull_request_reviews": {
                "required_approving_review_count": 1,
                "dismiss_stale_reviews": True,
                "require_last_push_approval": True,
            },
            "enforce_admins": {"enabled": True},
            "required_status_checks": {
                "strict": True,
                "checks": [
                    {"context": name, "app_id": 15368}
                    for name in ("safety (3.11)", "safety (3.12)", "validate", "ledger-tests",
                                 "security-regression", "failover-regression")
                ],
            },
            "allow_force_pushes": {"enabled": False},
            "allow_deletions": {"enabled": False},
        },
    }


class GovernanceTests(unittest.TestCase):
    def check(self, *, ctx=None, api=None):
        state = copy.deepcopy(responses() if api is None else api)
        requested = []

        def fetch(path):
            requested.append(path)
            return state[path]
        return assess_preflight(context() if ctx is None else ctx, fetch), requested

    def hold(self, expected, *, ctx=None, api=None):
        with self.assertRaisesRegex(GovernanceHold, expected):
            self.check(ctx=ctx, api=api)

    def test_approved_metadata_is_still_synthetic_hold(self):
        report, paths = self.check()
        self.assertEqual(paths, [BRANCH_ENDPOINT, PROTECTION_ENDPOINT])
        self.assertEqual(report["status"], "SYNTHETIC_SIGNER_GOVERNANCE_PREFLIGHT_OK")
        self.assertFalse(report["real_data_licence_verified"])
        self.assertFalse(report["real_signature_verified"])
        self.assertFalse(report["model_scoring_eligible"])
        self.assertFalse(report["positive_ev_verified"])
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_reject_untrusted_event_repo_ref_and_identity(self):
        overrides = {
            "GITHUB_REPOSITORY": "attacker/repository",
            "GITHUB_REPOSITORY_ID": "0",
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_REF": "refs/heads/feature",
            "GITHUB_REF_TYPE": "tag",
        }
        for key, value in overrides.items():
            with self.subTest(key=key):
                item = context()
                item[key] = value
                self.hold("UNTRUSTED_WORKFLOW_CONTEXT", ctx=item)

    def test_reject_bad_sha_and_run_identity(self):
        for key, bad in [
            ("GITHUB_SHA", "a" * 39), ("GITHUB_SHA", "b" * 40 + "\n"),
            ("GITHUB_RUN_ID", "0"), ("GITHUB_RUN_ID", "-4"),
            ("GITHUB_RUN_ID", "1;rm -rf /"), ("GITHUB_RUN_ATTEMPT", "0"),
            ("GITHUB_RUN_ATTEMPT", True),
        ]:
            with self.subTest(key=key, bad=bad):
                item = context()
                item[key] = bad
                self.hold("INVALID_RUN_|INVALID_RUN_COMMIT_SHA", ctx=item)

    def test_unprotected_main_blocks_before_other_api_calls(self):
        state = responses()
        state[BRANCH_ENDPOINT]["protected"] = False
        requested = []
        def fetch(path):
            requested.append(path)
            return state[path]
        with self.assertRaisesRegex(GovernanceHold, "MAIN_BRANCH_NOT_PROTECTED"):
            assess_preflight(context(), fetch)
        self.assertEqual(requested, [BRANCH_ENDPOINT])

    def test_reject_head_drift_and_wrong_metadata(self):
        for mutation, expected in [
            (("commit", {"sha": "b" * 40}), "MAIN_HEAD_DRIFT"),
            (("name", "not-main"), "WRONG_BRANCH_METADATA"),
            (("protected", "true"), "MAIN_BRANCH_NOT_PROTECTED"),
        ]:
            api = responses()
            api[BRANCH_ENDPOINT][mutation[0]] = mutation[1]
            self.hold(expected, api=api)

    def test_require_real_independent_reviews_and_fresh_approval(self):
        for key, value, expected in [
            ("required_approving_review_count", 0, "INDEPENDENT_REVIEW"),
            ("required_approving_review_count", True, "INDEPENDENT_REVIEW"),
            ("dismiss_stale_reviews", False, "STALE_APPROVALS"),
            ("require_last_push_approval", False, "LAST_PUSH_REVIEW"),
        ]:
            with self.subTest(key=key):
                api = responses()
                api[PROTECTION_ENDPOINT]["required_pull_request_reviews"][key] = value
                self.hold(expected, api=api)
        api = responses()
        api[PROTECTION_ENDPOINT].pop("required_pull_request_reviews")
        self.hold("INDEPENDENT_REVIEW", api=api)

    def test_require_admin_enforcement_strict_ci_and_checks(self):
        for field, value, expected in [
            ("enforce_admins", {"enabled": False}, "ADMINS_BYPASS"),
            ("enforce_admins", None, "ADMINS_BYPASS"),
            ("required_status_checks", {"strict": False, "checks": ["safety"]},
             "STRICT_REQUIRED_CI"),
            ("required_status_checks", {"strict": True, "checks": []},
             "NO_APP_PINNED_REQUIRED_STATUS_CHECKS"),
        ]:
            api = responses()
            api[PROTECTION_ENDPOINT][field] = value
            self.hold(expected, api=api)

    def test_reject_unrelated_single_check_and_unbound_legacy_contexts(self):
        api = responses()
        api[PROTECTION_ENDPOINT]["required_status_checks"]["checks"] = [
            {"context": "unrelated-success", "app_id": 15368}]
        self.hold("MANDATORY_SECURITY_CHECKS_NOT_PINNED", api=api)
        api = responses()
        api[PROTECTION_ENDPOINT]["required_status_checks"] = {
            "strict": True, "contexts": [
                "safety (3.11)", "safety (3.12)", "validate", "ledger-tests"],
        }
        self.hold("NO_APP_PINNED_REQUIRED_STATUS_CHECKS", api=api)

    def test_all_mandatory_checks_must_be_bound_to_verified_github_app(self):
        for name in ("safety (3.11)", "safety (3.12)", "validate", "ledger-tests",
                     "security-regression", "failover-regression"):
            with self.subTest(check=name):
                api = responses()
                checks = api[PROTECTION_ENDPOINT]["required_status_checks"]["checks"]
                next(x for x in checks if x["context"] == name)["app_id"] = 0
                self.hold("REQUIRED_CHECK_SOURCE_UNTRUSTED", api=api)
        api = responses()
        api[PROTECTION_ENDPOINT]["required_status_checks"]["checks"].append(
            {"context": "validate", "app_id": 123})
        self.hold("CONFLICTING_REQUIRED_STATUS_CHECK_SOURCE", api=api)

    def test_both_regression_suites_required_with_distinct_app_bound_names(self):
        for name in ("security-regression", "failover-regression"):
            with self.subTest(missing=name):
                api = responses()
                checks = api[PROTECTION_ENDPOINT]["required_status_checks"]["checks"]
                api[PROTECTION_ENDPOINT]["required_status_checks"]["checks"] = [
                    x for x in checks if x["context"] != name
                ]
                self.hold("MANDATORY_SECURITY_CHECKS_NOT_PINNED", api=api)
        api = responses()
        api[PROTECTION_ENDPOINT]["required_status_checks"]["checks"].append(
            {"context": "regression", "app_id": 15368})
        self.check(api=api)  # Legacy non-required context cannot replace either suite.

    def test_missing_mandatory_and_malformed_app_checks_rejected(self):
        api = responses()
        api[PROTECTION_ENDPOINT]["required_status_checks"]["checks"].pop()
        self.hold("MANDATORY_SECURITY_CHECKS_NOT_PINNED", api=api)
        for bad in ({"context": "validate", "app_id": "15368"},
                    {"context": "fake"}, "safety (3.12)"):
            with self.subTest(bad=str(bad)):
                api = responses()
                api[PROTECTION_ENDPOINT]["required_status_checks"]["checks"].append(bad)
                self.hold("MALFORMED_REQUIRED_STATUS_CHECK", api=api)

    def test_reject_unverified_force_push_and_delete_controls(self):
        for field, bad, expected in [
            ("allow_force_pushes", {"enabled": True}, "FORCE_PUSH"),
            ("allow_force_pushes", None, "FORCE_PUSH"),
            ("allow_deletions", {"enabled": True}, "BRANCH_DELETE"),
            ("allow_deletions", None, "BRANCH_DELETE"),
        ]:
            api = responses()
            api[PROTECTION_ENDPOINT][field] = bad
            self.hold(expected, api=api)

    def test_inaccessible_protection_and_api_exceptions_fail_closed(self):
        api = responses()
        del api[PROTECTION_ENDPOINT]
        with self.assertRaisesRegex(GovernanceHold, "GITHUB_GOVERNANCE_API_UNAVAILABLE"):
            self.check(api=api)
        with self.assertRaisesRegex(GovernanceHold, "GITHUB_READ_TOKEN_MISSING"):
            github_api_fetch("")
        with self.assertRaisesRegex(GovernanceHold, "UNAPPROVED_GITHUB_API_PATH"):
            github_api_fetch("synthetic-token")("/repos/evil/repository")

    def test_workflow_requires_preflight_before_signer(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("python ops/vnext_pr09_signer_preflight.py", workflow)
        self.assertIn("test_vnext_pr09_signer_preflight.py", workflow)
        self.assertLess(workflow.index("python ops/vnext_pr09_signer_preflight.py"),
                        workflow.index("uses: actions/attest@"))
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn("github.event_name == 'workflow_dispatch'", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertNotIn("pull_request_target:", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertNotIn("secrets.", workflow)


if __name__ == "__main__":
    unittest.main()
