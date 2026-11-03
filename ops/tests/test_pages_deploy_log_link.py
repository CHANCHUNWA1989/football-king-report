"""S0 deploy log linkage is always read-only, never release authorization."""
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pages_deploy_log_link import receipt
from test_pages_artifact_readback import run as base_run


ID = 13238906916
SHA = "2faedd216703b6905fe24ec04f73cc9fadcb12e4"


def jobs():
    return {"total_count": 2, "jobs": [
        {"name": "publish", "id": 125976985772, "run_id": 41653331039,
         "status": "completed", "conclusion": "success",
         "steps": [{"name": "Deploy mobile site", "conclusion": "success"}]},
        {"name": "archive", "id": 125978205510, "run_id": 41653331039,
         "status": "completed", "conclusion": "success", "steps": []},
    ]}


def artifacts():
    return {"total_count": 2, "artifacts": [
        {"name": "github-pages", "id": ID, "expired": False,
         "size_in_bytes": 83657, "digest": "sha256:" + "a" * 64,
         "workflow_run": {"id": 41653331039}},
        {"name": "diagnostics", "id": 12, "expired": False},
    ]}


def log():
    messages = [
        "##[group]Run actions/deploy-pages@d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e",
        'Fetching artifact metadata for "github-pages" in this workflow run',
        "Creating Pages deployment with payload:",
        "{",
        f'\t"artifact_id": {ID},',
        f'\t"pages_build_version": "{SHA}",',
        '\t"oidc_token": "***"',
        "}",
        f"Created deployment for {SHA}, ID: {SHA}",
        "Getting Pages deployment status...",
        "Reported success!",
    ]
    return "".join(f"2026-11-03T14:26:{i:02d}.1200000Z {x}\n"
                   for i, x in enumerate(messages)).encode()


class DeployLogLinkTests(unittest.TestCase):
    def check(self, meta=None, job=None, artifact=None, log_bytes=None):
        return receipt(base_run() if meta is None else meta,
                       jobs() if job is None else job,
                       artifacts() if artifact is None else artifact,
                       log() if log_bytes is None else log_bytes)

    def test_valid_github_log_correlates_but_never_approves_release(self):
        x = self.check()
        self.assertEqual(x["status"], "GITHUB_DEPLOY_LOG_ARTIFACT_SHA_CORRELATED_NOT_RELEASE")
        self.assertEqual(x["run_head_sha"], SHA)
        self.assertEqual(x["pages_artifact_id"], ID)
        self.assertTrue(x["github_deploy_payload_and_success_seen"])
        self.assertFalse(x["independent_deployment_identity_attested"])
        self.assertFalse(x["release_authorized"])
        self.assertFalse(x["verified_positive_ev"])
        self.assertEqual(x["production_recommendations"], "DISABLED")

    def test_wrong_artifact_id_is_hold(self):
        a = artifacts()
        a["artifacts"][0]["id"] += 1
        self.assertIn("S0_DEPLOY_RUN_ARTIFACT_OR_SHA_MISMATCH",
                      self.check(artifact=a)["reason"])

    def test_wrong_deployment_head_is_hold(self):
        meta = base_run()
        meta["head_sha"] = "d" * 40
        self.assertIn("S0_DEPLOY_RUN_ARTIFACT_OR_SHA_MISMATCH",
                      self.check(meta=meta)["reason"])

    def test_wrong_run_artifact_link_is_hold(self):
        a = artifacts()
        a["artifacts"][0]["workflow_run"]["id"] = 41653331040
        self.assertIn("S0_DEPLOY_ARTIFACT_WRONG_RUN",
                      self.check(artifact=a)["reason"])

    def test_no_reported_success_is_hold(self):
        tampered = log().replace(b"Reported success!", b"Deployment pending")
        self.assertIn("S0_DEPLOY_RUN_ARTIFACT_OR_SHA_MISMATCH",
                      self.check(log_bytes=tampered)["reason"])

    def test_wrong_order_log_is_hold(self):
        lines = log().splitlines(keepends=True)
        lines[-1], lines[-2] = lines[-2], lines[-1]
        self.assertIn("S0_DEPLOY_RUN_ARTIFACT_OR_SHA_MISMATCH",
                      self.check(log_bytes=b"".join(lines))["reason"])

    def test_missing_publish_job_is_hold(self):
        j = jobs()
        j["jobs"][0]["name"] = "other"
        self.assertIn("S0_DEPLOY_PUBLISH_JOB_UNVERIFIED", self.check(job=j)["reason"])

    def test_deploy_step_not_success_is_hold(self):
        j = jobs()
        j["jobs"][0]["steps"][0]["conclusion"] = "failure"
        self.assertIn("S0_DEPLOY_STEP_UNVERIFIED", self.check(job=j)["reason"])

    def test_incomplete_jobs_is_hold(self):
        j = jobs()
        j["total_count"] = 10
        self.assertIn("S0_DEPLOY_JOBS_RESPONSE_INCOMPLETE", self.check(job=j)["reason"])

    def test_incomplete_artifacts_is_hold(self):
        a = artifacts()
        a["total_count"] = 10
        self.assertIn("S0_DEPLOY_ARTIFACTS_INCOMPLETE", self.check(artifact=a)["reason"])

    def test_expired_artifact_is_hold(self):
        a = artifacts()
        a["artifacts"][0]["expired"] = True
        self.assertIn("S0_DEPLOY_PAGES_ARTIFACT_INVALID", self.check(artifact=a)["reason"])

    def test_duplicate_pages_artifact_is_hold(self):
        a = artifacts()
        a["artifacts"].append(copy.deepcopy(a["artifacts"][0]))
        a["total_count"] = len(a["artifacts"])
        self.assertIn("S0_DEPLOY_PAGES_ARTIFACT_INVALID", self.check(artifact=a)["reason"])

    def test_malformed_log_is_hold(self):
        self.assertEqual(self.check(log_bytes=b"untrusted text\n")["status"],
                         "HOLD_DEPLOY_IDENTITY_EVIDENCE_INCOMPLETE")

    def test_wrong_repo_is_hold(self):
        meta = base_run()
        meta["repository"]["full_name"] = "attacker/other"
        self.assertIn("S0_WRONG_REPOSITORY", self.check(meta=meta)["reason"])


if __name__ == "__main__":
    unittest.main()
