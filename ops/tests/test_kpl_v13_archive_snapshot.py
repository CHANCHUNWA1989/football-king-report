"""KPL V13 synthetic adversarial tests: one-read archive snapshots and fail-closed audit."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.kpl_v11_forecast_archive import archive_forecast
from research.kpl_v12_anchor_qualification import (
    build_anchor_request, inspect_anchor_receipt, screen_holdout_qualification)
from research.kpl_v13_archive_snapshot import read_verified_archive_snapshot
from ops.tests.test_kpl_v12_anchor_qualification import (
    synthetic_forecast, synthetic_result, make_archive)


class KPLV13SnapshotTests(unittest.TestCase):
    def test_snapshot_reads_valid_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            path, rows, _, _ = make_archive(folder, n_series=2)
            snapshot = read_verified_archive_snapshot(path)
            self.assertEqual(len(snapshot["entries"]), len(rows))
            self.assertEqual(snapshot["records"], rows)
            self.assertEqual(len(snapshot["archive_sha256"]), 64)
            self.assertEqual(snapshot["head_hash"],
                             snapshot["entries"][-1]["entry_hash"])

    def test_missing_archive_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "missing archive"):
                read_verified_archive_snapshot(Path(folder) / "absent.jsonl")

    def test_reject_duplicate_json_object_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "one.jsonl"
            archive_forecast(path, synthetic_forecast())
            text = path.read_text()
            self.assertIn('"probability":0.55', text)
            path.write_text(text.replace('"probability":0.55',
                                         '"probability":0.55,"probability":0.55', 1))
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                read_verified_archive_snapshot(path)

    def test_reject_modified_prob_without_hash_update(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "one.jsonl"
            archive_forecast(path, synthetic_forecast())
            value = json.loads(path.read_text().strip())
            value["forecast"]["probability"] = 0.98
            path.write_text(json.dumps(value) + "\n")
            with self.assertRaisesRegex(ValueError, "chain mismatch"):
                read_verified_archive_snapshot(path)

    def test_reject_truncated_last_line(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "one.jsonl"
            archive_forecast(path, synthetic_forecast())
            path.write_bytes(path.read_bytes().rstrip(b"\n"))
            with self.assertRaisesRegex(ValueError, "truncated archive"):
                read_verified_archive_snapshot(path)

    def test_reject_invalid_json_line(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.jsonl"
            path.write_bytes(b"not-json\n")
            with self.assertRaisesRegex(ValueError, "invalid archive JSON"):
                read_verified_archive_snapshot(path)

    def test_oversized_archive_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "too-big.jsonl"
            path.write_bytes(b"x" * 4097)
            with self.assertRaisesRegex(ValueError, "oversized archive"):
                read_verified_archive_snapshot(path, max_bytes=4096)

    def test_single_open_for_anchor_request(self):
        with tempfile.TemporaryDirectory() as folder:
            path, rows, _, receipts = make_archive(folder, n_series=2)
            original = Path.open
            opens = []
            def count_open(self, *args, **kwargs):
                if self == path:
                    opens.append(1)
                return original(self, *args, **kwargs)
            with patch.object(Path, "open", count_open):
                req = build_anchor_request(path, 1,
                                           requested_at=receipts[0]["received_at"])
            self.assertEqual(len(opens), 1, "must not re-open verified archive")
            self.assertEqual(req["prediction_id"], rows[0]["prediction_id"])

    def test_single_open_for_all_receipts_preflight(self):
        with tempfile.TemporaryDirectory() as folder:
            path, _, results, receipts = make_archive(folder)
            original = Path.open
            opens = []
            def count_open(self, *args, **kwargs):
                if self == path:
                    opens.append(1)
                return original(self, *args, **kwargs)
            with patch.object(Path, "open", count_open):
                res = screen_holdout_qualification(path, results, receipts,
                                                   train_fraction=0.5, min_test=2)
            self.assertEqual(len(opens), 1, "must verify receipts against same snapshot")
            self.assertTrue(res["technical_preflight_passed"])
            self.assertEqual(res["status"], "HOLD")
            self.assertFalse(res["external_witness_authenticated"])

    def test_reject_duplicate_keys_in_receipt_preflight(self):
        with tempfile.TemporaryDirectory() as folder:
            path, _, results, receipts = make_archive(folder)
            edited = dict(receipts[0])
            edited["head_hash"] = "f" * 64
            receipts[0] = edited
            r = screen_holdout_qualification(path, results, receipts, min_test=2)
            self.assertFalse(r["technical_preflight_passed"])
            self.assertIn("ANCHOR_RECEIPT_INVALID", r["reasons"])

    def test_plaintext_witness_cannot_promote_to_trust(self):
        with tempfile.TemporaryDirectory() as folder:
            path, _, _, receipts = make_archive(folder, n_series=2)
            receipt = dict(receipts[0])
            receipt["issuer_id"] = "official-claimed"
            r = inspect_anchor_receipt(path, receipt)
            self.assertTrue(r["structural_consistency_passed"])
            self.assertFalse(r["external_witness_authenticated"])
            self.assertEqual(r["status"], "HOLD")

    def test_no_production_flip_after_eligibility(self):
        with tempfile.TemporaryDirectory() as folder:
            path, _, results, receipts = make_archive(folder)
            r = screen_holdout_qualification(path, results, receipts,
                                             min_test=2, train_fraction=0.5)
            self.assertFalse(r["live_execution_allowed"])
            self.assertEqual(r["production_recommendations"], "DISABLED")
            self.assertFalse(r["provider_data_rights_verified"])


if __name__ == "__main__":
    unittest.main()
