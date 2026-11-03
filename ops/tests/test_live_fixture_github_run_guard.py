"""Mock-GitHub CLI policy tests; synthetic responses are NOT live evidence."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import live_fixture_github_run_guard as gate


class LiveFixtureRunGuardTests(unittest.TestCase):
    def setUp(self):
        self.kickoff = datetime(2026, 11, 4, 8, 0, tzinfo=timezone.utc)
        self.now = self.kickoff + timedelta(minutes=30)
        self.pins = dict(source_sha="1" * 40, run_id="123456789",
                         attempt="1", recorded_kickoff_utc=self.kickoff.isoformat(),
                         now=self.now)
        self.run = {
            "id": 123456789,
            "run_attempt": 1,
            "path": gate.WORKFLOW,
            "head_branch": "main",
            "head_sha": self.pins["source_sha"],
            "event": "workflow_dispatch",
            "status": "completed",
            "conclusion": "success",
            "created_at": "2026-11-04T07:30:00Z",
            "run_started_at": "2026-11-04T07:32:00Z",
            "repository": {"id": gate.REPOSITORY_ID, "full_name": gate.REPOSITORY},
            "head_repository": {"id": gate.REPOSITORY_ID, "full_name": gate.REPOSITORY},
        }

    def audit(self, value=None, returncode=0, **overrides):
        run = self.run if value is None else value
        with patch.object(gate.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], returncode, json.dumps(run).encode(), b"PRIVATE_TOKEN")) as mocked:
            result = gate.audit_github_run(**dict(self.pins, **overrides))
        return result, mocked

    def assert_hold(self, value):
        self.assertEqual(value["status"], "HOLD")
        self.assertFalse(value["github_run_metadata_correlated"])
        self.assertFalse(value["actual_kickoff_authenticated"])
        self.assertFalse(value["fixture_source_authenticated"])
        self.assertFalse(value["certified_positive_ev"])
        self.assertEqual(value["production_recommendations"], "DISABLED")

    def test_valid_mock_response_only_correlates_run_context(self):
        result, mocked = self.audit()
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertTrue(result["github_run_metadata_correlated"])
        self.assertFalse(result["actual_kickoff_authenticated"])
        self.assertFalse(result["market_executable_verified"])
        self.assertFalse(result["certified_positive_ev"])
        self.assertEqual(mocked.call_count, 1)
        argv = mocked.call_args.args[0]
        self.assertEqual(argv[:5], ["gh", "api", "--hostname", "github.com", "--method"])
        self.assertEqual(argv[-1], "/repos/" + gate.REPOSITORY + "/actions/runs/123456789")
        self.assertFalse(mocked.call_args.kwargs["shell"])
        self.assertEqual(mocked.call_args.kwargs["timeout"], 20)
        self.assertNotIn("PRIVATE_TOKEN", json.dumps(result))

    def test_wrong_repo_or_run_identity_fails_closed(self):
        for field, bad in [
            ("id", 123456790), ("id", "123456789"),
            ("repository", {"id": 100, "full_name": gate.REPOSITORY}),
            ("head_repository", None),
        ]:
            with self.subTest(field=field, bad=bad):
                row = copy.deepcopy(self.run)
                row[field] = bad
                result, _ = self.audit(row)
                self.assert_hold(result)
                self.assertEqual(result["reason"], "GITHUB_RUN_REPOSITORY_OR_ID_MISMATCH")

    def test_forged_source_workflow_branch_or_event_rejected(self):
        for field, bad in [
            ("path", ".github/workflows/other.yml"), ("head_branch", "feature/unsafe"),
            ("head_sha", "f" * 40), ("event", "pull_request"), ("run_attempt", 2),
            ("run_attempt", True),
        ]:
            with self.subTest(field=field, bad=bad):
                row = copy.deepcopy(self.run)
                row[field] = bad
                result, _ = self.audit(row)
                self.assert_hold(result)
                self.assertEqual(result["reason"], "GITHUB_RUN_SOURCE_CONTEXT_MISMATCH")

    def test_failed_or_running_workflow_rejected(self):
        for value in [("in_progress", None), ("completed", "failure"),
                      ("completed", "cancelled"), ("queued", None)]:
            with self.subTest(status=value):
                row = copy.deepcopy(self.run)
                row["status"], row["conclusion"] = value
                result, _ = self.audit(row)
                self.assert_hold(result)
                self.assertEqual(result["reason"], "GITHUB_RUN_NOT_SUCCESSFUL")

    def test_run_started_after_prematch_witness_window_is_hold(self):
        row = copy.deepcopy(self.run)
        row["run_started_at"] = "2026-11-04T07:55:00Z"
        result, _ = self.audit(row)
        self.assert_hold(result)
        self.assertEqual(result["reason"], "GITHUB_RUN_NOT_STARTED_EARLY_ENOUGH")

    def test_run_started_before_creation_or_in_future_is_hold(self):
        for bad in ("2026-11-04T07:20:00Z", "2026-11-04T09:50:00Z"):
            with self.subTest(bad=bad):
                row = copy.deepcopy(self.run)
                row["run_started_at"] = bad
                result, _ = self.audit(row)
                self.assert_hold(result)
                self.assertEqual(result["reason"], "GITHUB_RUN_CLOCK_ORDER_INVALID")

    def test_invalid_provenance_pins_do_not_make_network_request(self):
        for field, bad in [("run_id", "../../passwd"), ("attempt", 0),
                           ("source_sha", "1" * 39), ("source_sha", "g" * 40)]:
            with self.subTest(field=field):
                with patch.object(gate.subprocess, "run") as mocked:
                    result = gate.audit_github_run(**dict(self.pins, **{field: bad}))
                self.assert_hold(result)
                mocked.assert_not_called()

    def test_unavailable_api_and_bad_status_fail_closed(self):
        for failure in (FileNotFoundError(), subprocess.TimeoutExpired("gh", 20)):
            with self.subTest(kind=type(failure).__name__):
                with patch.object(gate.subprocess, "run", side_effect=failure):
                    result = gate.audit_github_run(**self.pins)
                self.assert_hold(result)
        result, _ = self.audit(returncode=1)
        self.assert_hold(result)
        self.assertNotIn("PRIVATE_TOKEN", json.dumps(result))

    def test_rejects_malformed_json_and_duplicate_keys(self):
        for raw in (b"", b"not-json", b'{"id":1,"id":2}', b"{}", b"[]",
                    b'{"id":NaN}', b"x" * (gate.MAX_RESPONSE_BYTES + 1)):
            with self.subTest(raw=raw[:22]):
                with patch.object(gate.subprocess, "run", return_value=
                                  subprocess.CompletedProcess([], 0, raw, b"")):
                    result = gate.audit_github_run(**self.pins)
                self.assert_hold(result)

    def test_bad_or_naive_kickoff_and_clock_fail_closed(self):
        for kickoff in ("2026-11-04T08:00:00", "not-a-date", None):
            with self.subTest(kickoff=kickoff):
                result, _ = self.audit(recorded_kickoff_utc=kickoff)
                self.assert_hold(result)
        result, _ = self.audit(now=datetime(2026, 11, 4, 8, 30))
        self.assert_hold(result)


if __name__ == "__main__":
    unittest.main()
