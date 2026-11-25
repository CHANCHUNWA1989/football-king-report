"""Real 105-row baseline + synthetic candidate, single in-memory iPhone source.

All tests are offline. Mocked *strict* remote receipts test control flow,
NOT authenticated GitHub ref proof or a live remote archive canary.
"""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from unittest import mock
import subprocess
import sys
import tempfile
import unittest

from ops.mobile_shared_settlement import (
    CutoverHold, _assemble, _hash_canonical, preview_from_official_archive,
)


class MobileSharedSettlementTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]
        self.legacy_path = self.root / "evidence" / "settled.json"
        self.gates_path = self.root / "sources/seven_quality_gates_latest.json"
        self.market_path = self.root / "market/latest.json"
        self.original_bytes = self.legacy_path.read_bytes()
        self.old = json.loads(self.original_bytes)
        self.quality = json.loads(self.gates_path.read_text())
        self.market = json.loads(self.market_path.read_text())
        self.now = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)
        self.sha = "f" * 40

    def candidate(self):
        new = deepcopy(self.old)
        fixture = deepcopy(new["samples"][0])
        fixture["key"] = "synthetic/preview-only/not-a-real-football-result"
        fixture["fixture_result_source_independently_verified"] = False
        fixture["production_recommendations"] = "DISABLED"
        new["samples"].append(fixture)
        new["n"] = len(new["samples"])
        return new

    def receipt(self, doc=None, remote=False):
        doc = self.old if doc is None else doc
        return {
            "archive_head_sha": self.sha,
            "legacy_sha256": hashlib.sha256(self.original_bytes).hexdigest(),
            "combined_samples": len(doc["samples"]),
            "legacy_samples": len(self.old["samples"]),
            "archive_batches": 1,
            "remote_ref_checked": remote,
            "remote_ref_stable_during_read": remote,
            "production_recommendations": "DISABLED",
        }

    def assemble(self, doc):
        return _assemble(self.old, doc, self.receipt(doc),
                         self.quality, self.market, now=self.now)

    def test_actual_105_legacy_rows_are_preserved_and_not_published(self):
        self.assertGreaterEqual(self.old["n"], 105)
        result = self.assemble(deepcopy(self.old))
        self.assertEqual(result["legacy_samples"], self.old["n"])
        self.assertEqual(result["daily_scorecard_samples"], self.old["n"])
        self.assertEqual(result["official_readiness_samples"], self.old["n"])
        self.assertFalse(result["site_published"])
        self.assertFalse(result["source_switch_authorized"])
        self.assertEqual(self.legacy_path.read_bytes(), self.original_bytes)

    def test_one_synthetic_row_yields_shared_106_view_and_detects_old_split(self):
        doc = self.candidate()
        result = self.assemble(doc)
        self.assertEqual(result["legacy_samples"], self.old["n"])
        self.assertEqual(result["candidate_samples"], self.old["n"] + 1)
        self.assertEqual(result["daily_scorecard_samples"], self.old["n"] + 1)
        self.assertEqual(result["official_readiness_samples"], self.old["n"] + 1)
        self.assertTrue(result["candidate_same_input_count_parity"])
        self.assertTrue(result["current_workflow_source_split_detected"])
        self.assertEqual(result["canonical_settlement_sha256"], _hash_canonical(doc))
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["verified_final_scores"])

    def test_actual_builders_receive_the_same_candidate_object(self):
        import ops.mobile_settlement_parity_preflight as stage
        original_readiness = stage.build_public_readiness
        original_daily = stage.build_daily_scorecard
        captured = []
        def observe_readiness(doc, *args, **kw):
            captured.append(("readiness", id(doc)))
            return original_readiness(doc, *args, **kw)
        def observe_daily(doc, *args, **kw):
            captured.append(("daily", id(doc)))
            return original_daily(doc, *args, **kw)
        candidate = self.candidate()
        with mock.patch.object(stage, "build_public_readiness",
                               side_effect=observe_readiness), mock.patch.object(
                                   stage, "build_daily_scorecard",
                                   side_effect=observe_daily):
            self.assemble(candidate)
        self.assertEqual(captured[-2:], [("readiness", id(candidate)),
                                          ("daily", id(candidate))])

    def test_reject_missing_and_modified_old_evidence(self):
        candidate = self.candidate()
        candidate["samples"].pop(0)
        candidate["n"] -= 1
        with self.assertRaisesRegex(CutoverHold, "HISTORIC_SETTLEMENT_SAMPLE_MISSING"):
            self.assemble(candidate)
        changed = self.candidate()
        changed["samples"][0]["y"] = (changed["samples"][0]["y"] + 1) % 3
        with self.assertRaisesRegex(CutoverHold, "HISTORIC_SETTLEMENT_SAMPLE_MUTATED"):
            self.assemble(changed)

    def test_mismatched_receipt_is_not_report_parity_proof(self):
        doc = self.candidate()
        bad = self.receipt(doc)
        bad["combined_samples"] = len(doc["samples"]) - 1
        with self.assertRaisesRegex(CutoverHold, "ARCHIVE_RECEIPT_SAMPLE_COUNT_MISMATCH"):
            _assemble(self.old, doc, bad, self.quality, self.market, now=self.now)
        bad = self.receipt(doc)
        bad["legacy_samples"] -= 1
        with self.assertRaisesRegex(CutoverHold, "LEGACY_RECEIPT_SAMPLE_COUNT_MISMATCH"):
            _assemble(self.old, doc, bad, self.quality, self.market, now=self.now)

    def test_enabled_or_unverified_receipt_rejected(self):
        doc = self.candidate()
        bad = self.receipt(doc)
        bad["production_recommendations"] = "ENABLED"
        with self.assertRaisesRegex(CutoverHold, "UNSAFE_ARCHIVE_RECEIPT"):
            _assemble(self.old, doc, bad, self.quality, self.market, now=self.now)

    def test_public_entrypoint_refuses_remote_lookup_failure(self):
        with mock.patch("ops.mobile_shared_settlement.reconcile_official_remote",
                        side_effect=ValueError("ARCHIVE_REMOTE_REF_NOT_CONFIRMED")):
            with self.assertRaisesRegex(ValueError, "ARCHIVE_REMOTE_REF_NOT_CONFIRMED"):
                preview_from_official_archive(
                    self.legacy_path, self.root, self.sha,
                    self.gates_path, self.market_path, now=self.now)

    def test_public_entrypoint_requires_two_remote_checks(self):
        candidate = self.candidate()
        bad = self.receipt(candidate, remote=True)
        bad["remote_ref_stable_during_read"] = False
        with mock.patch("ops.mobile_shared_settlement.reconcile_official_remote",
                        return_value=(candidate, bad)):
            with self.assertRaisesRegex(CutoverHold, "OFFICIAL_ARCHIVE_READ_NOT_CONFIRMED"):
                preview_from_official_archive(
                    self.legacy_path, self.root, self.sha,
                    self.gates_path, self.market_path, now=self.now)

    def test_mocked_remote_can_only_prove_control_flow_not_real_authentication(self):
        candidate = self.candidate()
        receipt = self.receipt(candidate, remote=True)
        with mock.patch("ops.mobile_shared_settlement.reconcile_official_remote",
                        return_value=(candidate, receipt)):
            report = preview_from_official_archive(
                self.legacy_path, self.root, self.sha,
                self.gates_path, self.market_path, now=self.now)
        self.assertTrue(report["archive_ref_checked"])
        self.assertFalse(report["archive_ref_independently_attested"])
        self.assertFalse(report["source_switch_authorized"])
        self.assertFalse(report["site_published"])
        self.assertEqual(report["candidate_samples"], self.old["n"] + 1)

    def test_legacy_source_byte_swap_between_bridge_and_preview_rejected(self):
        candidate = self.candidate()
        receipt = self.receipt(candidate, remote=True)
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "legacy.json"
            legacy.write_bytes(self.original_bytes + b" ")
            # JSON content same, original bytes NOT same; fail before reports.
            with mock.patch("ops.mobile_shared_settlement.reconcile_official_remote",
                            return_value=(candidate, receipt)):
                with self.assertRaisesRegex(CutoverHold,
                                            "LEGACY_SOURCE_CHANGED_DURING_PREVIEW"):
                    preview_from_official_archive(
                        legacy, self.root, self.sha, self.gates_path,
                        self.market_path, now=self.now)

    def test_cli_fails_closed_without_real_verified_remote_archive(self):
        proc = subprocess.run([
            sys.executable, "-m", "ops.mobile_shared_settlement",
            "--legacy", str(self.legacy_path),
            "--archive-checkout", str(self.root),
            "--expected-archive-sha", self.sha,
            "--gates", str(self.gates_path),
            "--market", str(self.market_path),
        ], cwd=self.root, capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)["status"],
                         "HOLD_OFFICIAL_SHARED_SNAPSHOT_NOT_VERIFIED")
        self.assertNotIn("samples", proc.stdout)
        self.assertEqual(self.legacy_path.read_bytes(), self.original_bytes)


if __name__ == "__main__":
    unittest.main()
