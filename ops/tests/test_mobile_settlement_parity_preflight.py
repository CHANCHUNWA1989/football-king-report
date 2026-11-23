"""Real iPhone report builders vs actual checked-in 105+ research cases.

No provider, external API, GitHub remote, archive ref or production-site write.
"""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from ops.mobile_settlement_parity_preflight import CutoverHold, preflight


class MobileSettlementParityPreflightTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]
        self.legacy_path = self.root / "evidence" / "settled.json"
        self.workflow = self.root / ".github" / "workflows" / "football-king-iphone.yml"
        self.legacy = json.loads(self.legacy_path.read_text(encoding="utf-8"))
        self.quality = json.loads(
            (self.root / "sources/seven_quality_gates_latest.json").read_text())
        self.market = json.loads((self.root / "market/latest.json").read_text())
        self.now = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)
        self.original = self.legacy_path.read_bytes()

    def run_check(self, candidate):
        return preflight(self.legacy, candidate, self.quality, self.market,
                         now=self.now)

    def candidate_with_one_new_synthetic_row(self):
        doc = deepcopy(self.legacy)
        # A distinct *synthetic research fixture*; duplicate event time is
        # deliberate to avoid inventing a genuine scored football result.
        added = deepcopy(doc["samples"][0])
        added["key"] = "synthetic/mobile-cutover-parity-only/never-real-fixture"
        added["fixture_result_source_independently_verified"] = False
        added["production_recommendations"] = "DISABLED"
        doc["samples"].append(added)
        doc["n"] = len(doc["samples"])
        return doc

    def test_real_repository_legacy_replay_keeps_both_report_counts_equal(self):
        self.assertGreaterEqual(self.legacy["n"], 105)
        result = self.run_check(deepcopy(self.legacy))
        self.assertEqual(result["status"], "RESEARCH_PARITY_BASELINE_ONLY_NOT_DEPLOYED")
        self.assertEqual(result["legacy_sample_count"], self.legacy["n"])
        self.assertEqual(result["candidate_daily_scorecard_count"], self.legacy["n"])
        self.assertEqual(result["candidate_public_readiness_count_if_switched"],
                         self.legacy["n"])
        self.assertTrue(result["current_workflow_count_parity"])
        self.assertFalse(result["live_iphone_cutover_completed"])
        self.assertEqual(self.legacy_path.read_bytes(), self.original)

    def test_synthetic_new_batch_exposes_current_workflow_two_source_split(self):
        doc = self.candidate_with_one_new_synthetic_row()
        result = self.run_check(doc)
        self.assertEqual(result["status"], "HOLD_CURRENT_WORKFLOW_SOURCE_SPLIT")
        self.assertEqual(result["legacy_main_public_readiness_count"], self.legacy["n"])
        self.assertEqual(result["candidate_daily_scorecard_count"], self.legacy["n"]+1)
        self.assertEqual(result["candidate_public_readiness_count_if_switched"],
                         self.legacy["n"]+1)
        self.assertFalse(result["current_workflow_count_parity"])
        self.assertTrue(result["candidate_same_input_count_parity"])
        self.assertFalse(result["source_switch_authorized"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_inferred_current_iPhone_route_is_verified_against_source(self):
        source = self.workflow.read_text(encoding="utf-8")
        self.assertIn('--previous evidence/settled.json', source)
        self.assertIn('--settled evidence/settled.json', source)
        self.assertIn('--input "$RUNNER_TEMP/settled.json"', source)
        self.assertIn('ops/public_readiness_site', source)
        self.assertIn('ops/forward_daily_scorecard.py', source)

    def test_replacing_old_result_is_not_mobile_read_compatibility(self):
        doc = deepcopy(self.legacy)
        doc["samples"][0]["y"] = (doc["samples"][0]["y"]+1)%3
        with self.assertRaisesRegex(CutoverHold, "HISTORIC_SETTLEMENT_SAMPLE_MUTATED"):
            self.run_check(doc)

    def test_dropping_old_sample_rejected(self):
        doc = deepcopy(self.legacy)
        doc["samples"].pop()
        doc["n"] = len(doc["samples"])
        with self.assertRaisesRegex(CutoverHold, "HISTORIC_SETTLEMENT_SAMPLE_MISSING"):
            self.run_check(doc)

    def test_unsafe_production_label_is_rejected(self):
        doc = deepcopy(self.legacy)
        doc["production_recommendations"] = "ENABLED"
        with self.assertRaisesRegex(ValueError, "INVALID_EVIDENCE_SAFETY"):
            self.run_check(doc)

    def test_unsafe_incoming_row_production_flag_is_rejected(self):
        doc = self.candidate_with_one_new_synthetic_row()
        doc["samples"][-1]["production_recommendations"] = "ENABLED"
        with self.assertRaisesRegex(ValueError, "UNSAFE_SETTLEMENT"):
            self.run_check(doc)

    def test_duplicate_fixture_key_does_not_count_twice(self):
        doc = self.candidate_with_one_new_synthetic_row()
        doc["samples"][-1]["key"] = doc["samples"][0]["key"]
        with self.assertRaisesRegex(ValueError, "DUPLICATE_EVIDENCE_KEY"):
            self.run_check(doc)

    def test_legacy_and_candidate_files_remain_unchanged(self):
        doc = self.candidate_with_one_new_synthetic_row()
        before = json.dumps(doc, sort_keys=True)
        self.run_check(doc)
        self.assertEqual(json.dumps(doc, sort_keys=True), before)
        self.assertEqual(self.legacy_path.read_bytes(), self.original)

    def test_cli_is_fail_closed_on_synthetic_source_split(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            candidate = root / "candidate.json"
            candidate.write_text(json.dumps(self.candidate_with_one_new_synthetic_row()))
            quality = root / "quality.json"
            quality.write_text(json.dumps(self.quality))
            market = root / "market.json"
            market.write_text(json.dumps(self.market))
            args = [sys.executable, "-m", "ops.mobile_settlement_parity_preflight",
                    "--legacy", str(self.legacy_path), "--candidate", str(candidate),
                    "--gates", str(quality), "--market", str(market)]
            proc = subprocess.run(args, cwd=self.root, capture_output=True,
                                  text=True, check=False)
            self.assertEqual(proc.returncode, 1, proc.stderr[:250])
            receipt = json.loads(proc.stdout)
            self.assertEqual(receipt["status"], "HOLD_CURRENT_WORKFLOW_SOURCE_SPLIT")
            self.assertEqual(receipt["production_recommendations"], "DISABLED")
        self.assertEqual(self.legacy_path.read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main()
