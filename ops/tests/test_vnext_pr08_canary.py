"""PR-08: offline synthetic canary and restricted signer workflow checks.

These tests cannot validate real Sigstore signing or third-party data rights.
They deliberately require all generated data to remain synthetic and DISABLED.
"""
import copy
import hashlib
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vnext_pr08_canary import SYNTHETIC_PREFIX, generate_canary
from vnext_prospective_local_seal import read_forecast_seal

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "football-king-vnext-forecast-attest.yml"
FIXED_CLOCK = datetime(2026, 11, 4, 8, 0, 0, tzinfo=UTC)


class CanaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "new-only"

    def _make(self, *, now=FIXED_CLOCK):
        return generate_canary(self.root, 12345, 1, now=now)

    def test_synthetic_seal_integrity_and_no_promotions(self):
        item = self._make()
        self.assertTrue(item["synthetic_test_only"])
        self.assertFalse(item["eligible_for_model_scoring"])
        self.assertFalse(item["positive_ev_verified"])
        self.assertEqual(item["production_recommendations"], "DISABLED")
        self.assertTrue(item["fixture_id"].startswith(SYNTHETIC_PREFIX))
        seal_file = self.root / item["file_name"]
        self.assertEqual(str(seal_file.resolve()), item["subject_path"])
        self.assertEqual(hashlib.sha256(seal_file.read_bytes()).hexdigest(), item["sha256"])
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        self.assertEqual(seal_file.stat().st_mode & 0o777, 0o600)
        record = read_forecast_seal(self.root, item["file_name"], expected_sha256=item["sha256"])
        self.assertEqual(record["pair"]["fixture_id"], item["fixture_id"])
        self.assertFalse(record["external_clock_attested"])
        self.assertFalse(record["source_independence_authenticated"])
        self.assertFalse(record["source_rights_independently_verified"])
        self.assertFalse(record["results_contained"])
        self.assertEqual(record["production_recommendations"], "DISABLED")
        self.assertEqual(record["source_refs"][0]["rights_scope"], "DERIVED_METADATA_ONLY_UNVERIFIED")
        self.assertEqual(record["source_refs"][0]["provider"], "synthetic-pr08-provider")
        self.assertEqual(set(record["pair"]["models"]), {"baseline", "challenger"})
        for model in record["pair"]["models"].values():
            self.assertFalse(model["calibrated"])
            self.assertEqual(model["production_recommendations"], "DISABLED")

    def test_forecast_time_precedes_fictional_kickoff(self):
        item = self._make()
        record = read_forecast_seal(self.root, item["file_name"], expected_sha256=item["sha256"])
        pair = record["pair"]
        self.assertEqual(pair["as_of_utc"], "2026-11-04T07:59:30Z")
        self.assertEqual(pair["kickoff_utc"], "2026-11-04T11:00:00Z")
        self.assertEqual(record["recorded_at_utc"], "2026-11-04T08:00:00Z")

    def test_refuse_existing_output_and_preexisting_symlink(self):
        self._make()
        with self.assertRaisesRegex(ValueError, "CANARY_OUTPUT_MUST_BE_NEW"):
            self._make()
        other = Path(self.tmp.name) / "alias"
        other.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "CANARY_OUTPUT_MUST_BE_NEW"):
            generate_canary(other, 12345, 1, now=FIXED_CLOCK)

    def test_run_identity_rejects_bool_zero_negative_and_oversized(self):
        for rid, attempt in ((True, 1), (0, 1), (-1, 1), (10**15, 1),
                             (1, False), (1, 0), (1, -2), (1, 1000)):
            with self.subTest(rid=rid, attempt=attempt):
                with self.assertRaisesRegex(ValueError, "INVALID_CANARY_RUN_IDENTITY"):
                    generate_canary(self.root, rid, attempt, now=FIXED_CLOCK)
                self.assertFalse(self.root.exists())

    def test_naive_and_non_utc_clock_refused(self):
        for value in (FIXED_CLOCK.replace(tzinfo=None),
                      FIXED_CLOCK.astimezone(timezone(timedelta(hours=8))),
                      "2026-11-04T08:00:00Z"):
            with self.subTest(clock=str(value)):
                with self.assertRaisesRegex(ValueError, "CANARY_REQUIRES_UTC"):
                    generate_canary(self.root, 12345, 1, now=value)
                self.assertFalse(self.root.exists())

    def test_detect_post_seal_content_tampering(self):
        item = self._make()
        path = self.root / item["file_name"]
        path.write_bytes(path.read_bytes().replace(b"synthetic-pr08-provider", b"synthetic-pr08-intruder"))
        with self.assertRaisesRegex(ValueError, "ARCHIVE_INTEGRITY"):
            read_forecast_seal(self.root, item["file_name"], expected_sha256=item["sha256"])


class WorkflowGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.yaml = WORKFLOW.read_text(encoding="utf-8")

    def test_explicit_manual_dispatch_only(self):
        head = self.yaml.split("permissions:", 1)[0]
        self.assertIn("workflow_dispatch:", head)
        for forbidden in ("push:", "pull_request:", "schedule:", "workflow_run:"):
            self.assertNotIn(forbidden, head)
        self.assertIn("github.ref == 'refs/heads/main'", self.yaml)
        self.assertIn("github.event_name == 'workflow_dispatch'", self.yaml)
        self.assertIn("github.repository == 'CHANCHUNWA1989/football-king-report'", self.yaml)

    def test_least_privilege_and_synthetic_only_workflow(self):
        self.assertIn("persist-credentials: false", self.yaml)
        self.assertIn("id-token: write", self.yaml)
        self.assertIn("attestations: write", self.yaml)
        self.assertIn("artifact-metadata: write", self.yaml)
        self.assertIn("test_vnext_pr08_canary.py", self.yaml)
        self.assertIn("vnext_pr08_canary.py", self.yaml)
        self.assertIn("vnext_forecast_attestation_gate import audit_witness", self.yaml)
        self.assertIn("subject-path: ${{ steps.canary.outputs.subject_path }}", self.yaml)
        self.assertIn("report.get(\"production_recommendations\") != \"DISABLED\"", self.yaml)
        self.assertIn("if-no-files-found: error", self.yaml)
        self.assertNotIn("pull_request_target", self.yaml)
        self.assertNotIn("secrets.", self.yaml)
        self.assertNotIn("betting_enabled: true", self.yaml)


if __name__ == "__main__":
    unittest.main()
