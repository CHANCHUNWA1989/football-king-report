"""S2 site-readback negative tests use synthetic data only; no provider access."""
import copy
from datetime import datetime, timezone
import unittest

from ops.control_tower_site_readback import (
    API_ROOT, DEPLOY_WORKFLOW, evaluate_readback, get_json, select_deploy,
    strict_object, utc_clock, SHA40
)

NOW = datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)
SHA = "a" * 40
RUN_ID = 1001


def good():
    return {
        "branch": {"protected": True, "commit": {"sha": SHA}},
        "status": {
            "checked_utc": "2026-11-03T14:30:00Z", "production_recommendations": "DISABLED",
            "status": "RESEARCH_ONLY", "quality_status": "RESEARCH_ONLY",
            "window_matches": 20, "source_commit_sha": SHA,
        },
        "quality": {
            "checked_utc": "2026-11-03T14:30:00Z", "production_recommendations": "DISABLED",
            "status": "RESEARCH_ONLY", "critical_errors": [],
            "public_matches": 20, "matches_with_precise_kickoff": 10,
            "pre_match_snapshot_eligible": 8, "source_commit_sha": SHA,
        },
        "gate": {
            "status": "HOLD", "production_recommendations": "DISABLED",
            "automated_release_supported": False, "model_promoted": False,
            "source_commit_sha": SHA,
        },
        "runs": {
            "total_count": 1,
            "workflow_runs": [{
                "id": RUN_ID, "name": DEPLOY_WORKFLOW,
                "head_branch": "main", "head_sha": SHA, "event": "schedule",
                "created_at": "2026-11-03T14:28:00Z",
                "status": "completed", "conclusion": "success",
            }],
        },
        "jobs": {
            "total_count": 1,
            "jobs": [{
                "name": "publish", "run_id": RUN_ID,
                "status": "completed", "conclusion": "success",
                "steps": [{
                    "name": "Deploy mobile site", "status": "completed",
                    "conclusion": "success",
                }],
            }],
        },
    }


class SiteReadbackTests(unittest.TestCase):
    def evaluate(self, data, expected=SHA):
        return evaluate_readback(data, expected, now=NOW)

    def expect_blocker(self, data, blocker, expected=SHA):
        result = self.evaluate(data, expected=expected)
        self.assertEqual(result["status"], "HOLD")
        self.assertIn(blocker, result["blockers"])
        self.assertFalse(result["release_authorized"])
        self.assertFalse(result["pages_deployment_authorized"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_synthetic_green_still_not_release_authorization(self):
        result = self.evaluate(good())
        self.assertEqual(result["status"], "CONSISTENT_RESEARCH_ONLY_NOT_AUTHORIZED")
        self.assertEqual(result["blockers"], [])
        self.assertFalse(result["release_authorized"])
        self.assertFalse(result["live_execution_allowed"])
        self.assertFalse(result["verified_positive_ev"])

    def test_missing_data_always_holds(self):
        self.expect_blocker({}, "PUBLIC_SITE_DOCUMENTS_MISSING")

    def test_expected_sha_invalid(self):
        self.expect_blocker(good(), "EXPECTED_RELEASE_SHA_INVALID", "not-a-sha")

    def test_current_main_mismatch(self):
        data = good()
        data["branch"]["commit"]["sha"] = "b" * 40
        self.expect_blocker(data, "MAIN_RELEASE_SHA_NOT_CURRENT")

    def test_main_protection_not_set(self):
        data = good()
        data["branch"]["protected"] = False
        self.expect_blocker(data, "MAIN_PROTECTION_NOT_VERIFIED")

    def test_expired_site_clock(self):
        data = good()
        data["status"]["checked_utc"] = "2026-11-03T02:30:00Z"
        data["quality"]["checked_utc"] = "2026-11-03T02:30:00Z"
        self.expect_blocker(data, "SITE_CAPTURE_STALE_OR_FUTURE")

    def test_future_site_clock(self):
        data = good()
        data["status"]["checked_utc"] = "2026-11-03T15:08:00Z"
        data["quality"]["checked_utc"] = "2026-11-03T15:08:00Z"
        self.expect_blocker(data, "SITE_CAPTURE_STALE_OR_FUTURE")

    def test_clock_skew(self):
        data = good()
        data["quality"]["checked_utc"] = "2026-11-03T14:00:00Z"
        self.expect_blocker(data, "SITE_STATUS_QUALITY_CLOCK_MISMATCH")

    def test_naive_clock(self):
        data = good()
        data["status"]["checked_utc"] = "2026-11-03T14:30:00"
        self.expect_blocker(data, "SITE_CAPTURE_CLOCK_INVALID")

    def test_unsafe_production_flag(self):
        data = good()
        data["quality"]["production_recommendations"] = "ENABLED"
        self.expect_blocker(data, "PUBLIC_RECOMMENDATIONS_NOT_DISABLED")

    def test_production_gate_status_mismatch(self):
        data = good()
        data["gate"]["status"] = "READY"
        self.expect_blocker(data, "PUBLIC_PRODUCTION_GATE_NOT_HOLD")

    def test_model_promoted_wrong(self):
        data = good()
        data["gate"]["model_promoted"] = True
        self.expect_blocker(data, "PUBLIC_MODEL_PROMOTION_NOT_DISABLED")

    def test_source_hold_is_not_healthy(self):
        data = good()
        data["status"]["status"] = "HOLD"
        self.expect_blocker(data, "PUBLIC_RESEARCH_SOURCE_HOLD")

    def test_status_quality_different(self):
        data = good()
        data["status"]["quality_status"] = "HOLD"
        self.expect_blocker(data, "PUBLIC_QUALITY_STATE_MISMATCH")

    def test_quality_critical_error(self):
        data = good()
        data["quality"]["critical_errors"] = ["STALE"]
        self.expect_blocker(data, "PUBLIC_CRITICAL_QUALITY_ERRORS")

    def test_fixture_population_mismatch(self):
        data = good()
        data["quality"]["public_matches"] = 21
        self.expect_blocker(data, "PUBLIC_MATCH_COUNTS_INCONSISTENT")

    def test_invalid_eligible_count(self):
        data = good()
        data["quality"]["pre_match_snapshot_eligible"] = 15
        self.expect_blocker(data, "PUBLIC_ELIGIBILITY_COUNTS_INVALID")

    def test_missing_deploy_run(self):
        data = good()
        data["runs"]["workflow_runs"] = []
        self.expect_blocker(data, "EXACT_SHA_DEPLOY_RUN_UNVERIFIED")

    def test_wrong_branch_deploy_run(self):
        data = good()
        data["runs"]["workflow_runs"][0]["head_branch"] = "research"
        self.expect_blocker(data, "EXACT_SHA_DEPLOY_RUN_UNVERIFIED")

    def test_wrong_commit_deploy_run(self):
        data = good()
        data["runs"]["workflow_runs"][0]["head_sha"] = "f" * 40
        self.expect_blocker(data, "EXACT_SHA_DEPLOY_RUN_UNVERIFIED")

    def test_missing_deploy_step(self):
        data = good()
        data["jobs"]["jobs"][0]["steps"] = []
        self.expect_blocker(data, "PAGES_DEPLOY_STEP_NOT_VERIFIED")

    def test_failed_deploy_job(self):
        data = good()
        data["jobs"]["jobs"][0]["conclusion"] = "failure"
        self.expect_blocker(data, "DEPLOY_JOB_NOT_VERIFIED")

    def test_missing_version_marker(self):
        data = good()
        del data["status"]["source_commit_sha"]
        self.expect_blocker(data, "PUBLIC_SITE_RELEASE_SHA_NOT_ATTESTED")

    def test_forged_version_marker_detected(self):
        data = good()
        data["gate"]["source_commit_sha"] = "b" * 40
        self.expect_blocker(data, "PUBLIC_SITE_RELEASE_SHA_NOT_ATTESTED")

    def test_no_redirect_to_unapproved_host(self):
        with self.assertRaises(ValueError):
            get_json("https://example.net/release-notes.json")

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(ValueError):
            strict_object([("a", 1), ("a", 2)])

    def test_site_status_document_not_object(self):
        data = good()
        data["status"] = []
        self.expect_blocker(data, "PUBLIC_SITE_DOCUMENTS_MISSING")

    def test_bool_counts_rejected(self):
        data = good()
        data["quality"]["public_matches"] = True
        self.expect_blocker(data, "PUBLIC_MATCH_COUNTS_INCONSISTENT")

    def test_results_100_entries_fail_closed(self):
        data = good()
        data["runs"]["workflow_runs"] = data["runs"]["workflow_runs"] * 100
        self.expect_blocker(data, "DEPLOY_RUNS_INCOMPLETE")

    def test_invalid_time_zone_offset_rejected(self):
        self.assertIsNone(utc_clock("2026-11-03T22:30:00+08:00"))


if __name__ == "__main__":
    unittest.main()
