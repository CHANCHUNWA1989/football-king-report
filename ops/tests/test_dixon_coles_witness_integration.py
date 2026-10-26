"""Exercise genuine parser flow with mocked CLI bytes, never real signatures."""
import json
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dixon_coles_witness_audit import audit
from forecast_provenance_audit import audit as original_audit
from model_dixon_coles_forward import TOP_KEY, build
from test_dixon_coles_forward_integration import NOW, shadow_document
import test_forecast_provenance_audit as provenance_fixture


class DixonColesWitnessIntegrationTests(unittest.TestCase):
    def test_new_candidate_audit_preserves_proof_and_original_comparison_audit(self):
        fixture = provenance_fixture.ForecastProvenanceAuditTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.shadow = shadow_document()
        fixture.shadow[TOP_KEY] = build(fixture.shadow, now=NOW)
        fixture.paired = {"status": "HOLD", "matched_count": 0,
                          "comparisons": [], "production_recommendations": "DISABLED"}
        fixture.slate.update(verification_rows=0, point_in_time_market_pairs=0, rows=[])
        fixture.write_inputs()
        before = {p.name: p.read_bytes() for p in fixture.proof.iterdir()}
        stdout = fixture.stdout()
        stdout[0]["verificationResult"]["verifiedTimestamps"][0]["timestamp"] = "2026-10-26T10:00:01Z"
        completed = subprocess.CompletedProcess([], 0, json.dumps(stdout).encode(), b"")
        options = {**fixture.options,
                   "now": datetime(2026, 10, 26, 10, 1, tzinfo=timezone.utc)}
        with patch("forecast_provenance_audit.subprocess.run", return_value=completed):
            original_before = original_audit(fixture.proof, **options)
        with patch("forecast_provenance_audit.subprocess.run", return_value=completed) as runner:
            result = audit(fixture.proof, **options)
        self.assertEqual(runner.call_count, 3)
        self.assertTrue(result["audit_completed"])
        self.assertTrue(result["candidate_capture_present"])
        self.assertEqual(result["observed_before_recorded_kickoff_count"], 1)
        self.assertFalse(result["eligible_for_betting_promotion"])
        self.assertFalse(result["recorded_kickoff_independently_authenticated"])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        with patch("forecast_provenance_audit.subprocess.run", return_value=completed):
            original_after = original_audit(fixture.proof, **options)
        self.assertEqual(original_before, original_after)
        self.assertEqual(original_before["total_pairs"], 0)
        self.assertEqual(before, {p.name: p.read_bytes() for p in fixture.proof.iterdir()})

    def test_workflow_binds_new_audit_to_same_trusted_run_and_keeps_original_artifact(self):
        workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/football-king-iphone.yml").read_text()
        job = workflow.split("  archive_provenance:\n", 1)[1].split("\n  archive:\n", 1)[0]
        step = job.split("      - name: Reverify fixed candidate before auditing its recorded kickoff times\n", 1)[1]
        step = step.split("\n      - name:", 1)[0]
        for required in (
            "GH_TOKEN: ${{ github.token }}", "set -euo pipefail",
            "python ops/dixon_coles_witness_audit.py", "--proof proof",
            '--source-sha "$GITHUB_SHA"', '--workflow-sha "$GITHUB_WORKFLOW_SHA"',
            '--run-id "$GITHUB_RUN_ID"', '--attempt "$GITHUB_RUN_ATTEMPT"',
            '--output "$RUNNER_TEMP/dixon-coles-witness-audit.json"',
        ):
            self.assertIn(required, step)
        self.assertNotIn("continue-on-error", job)
        self.assertNotIn("secrets.", job)
        self.assertIn("name: football-king-provenance-time-audit", job)
        self.assertIn("name: football-king-dixon-coles-witness-audit", job)
        self.assertIn("path: ${{ runner.temp }}/dixon-coles-witness-audit.json", job)


if __name__ == "__main__":
    unittest.main()
