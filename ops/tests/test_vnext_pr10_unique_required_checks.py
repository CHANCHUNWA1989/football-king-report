"""PR-10 CI check names must be unique and pinned before protected-main signing.

Static/offline unit tests only, not an assertion that branch protection is set.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ops"))
from vnext_pr09_signer_preflight import (
    REQUIRED_CHECKS, GITHUB_ACTIONS_APP_ID, GovernanceHold,
    assess_preflight, BRANCH_ENDPOINT, PROTECTION_ENDPOINT,
)


def read(name):
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def job_ids(yaml_text):
    # This is a narrow static contract for the two simple, fully indented
    # current workflows. It must never serve as general YAML parsing.
    portion = yaml_text.split("\njobs:\n", 1)
    if len(portion) != 2:
        raise ValueError("NO_WORKFLOW_JOBS")
    return re.findall(r"(?m)^  ([A-Za-z0-9_-]+):\s*$", portion[1])


class UniqueCiCheckContracts(unittest.TestCase):
    def test_two_critical_regression_job_ids_are_unique(self):
        safety = read("football-king-ci.yml")
        failover = read("football-king-regression.yml")
        self.assertEqual(job_ids(safety), ["security-regression", "stress"])
        self.assertEqual(job_ids(failover), ["failover-regression"])
        self.assertNotIn("regression", job_ids(safety) + job_ids(failover))

    def test_both_workflows_are_triggered_on_ops_change(self):
        for name in ("football-king-ci.yml", "football-king-regression.yml"):
            with self.subTest(name=name):
                yaml = read(name)
                self.assertIn("pull_request:", yaml)
                self.assertIn("'ops/**'", yaml)
                self.assertIn("contents: read", yaml)

    def test_governance_requires_both_regression_checks(self):
        self.assertEqual(GITHUB_ACTIONS_APP_ID, 15368)
        self.assertEqual(REQUIRED_CHECKS, frozenset({
            "safety (3.11)", "safety (3.12)",
            "validate", "ledger-tests", "security-regression", "failover-regression",
        }))

    def test_single_duplicate_legacy_name_cannot_replace_critical_checks(self):
        context = {
            "GITHUB_REPOSITORY": "CHANCHUNWA1989/football-king-report",
            "GITHUB_REPOSITORY_ID": "1411226578",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_REF_TYPE": "branch",
            "GITHUB_SHA": "a" * 40,
            "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
        }
        branch = {
            "name": "main", "commit": {"sha": "a" * 40}, "protected": True,
        }
        protection = {
            "required_pull_request_reviews": {
                "required_approving_review_count": 1,
                "dismiss_stale_reviews": True,
                "require_last_push_approval": True,
            },
            "enforce_admins": {"enabled": True},
            "required_status_checks": {
                "strict": True,
                "checks": [
                    {"context": name, "app_id": GITHUB_ACTIONS_APP_ID}
                    for name in (
                        "safety (3.11)", "safety (3.12)",
                        "validate", "ledger-tests", "regression",
                    )
                ],
            },
            "allow_force_pushes": {"enabled": False},
            "allow_deletions": {"enabled": False},
        }
        def fetch(path):
            return {BRANCH_ENDPOINT: branch, PROTECTION_ENDPOINT: protection}[path]
        with self.assertRaisesRegex(GovernanceHold, "MANDATORY_SECURITY_CHECKS_NOT_PINNED"):
            assess_preflight(context, fetch)


if __name__ == "__main__":
    unittest.main()
