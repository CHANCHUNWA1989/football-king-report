"""External receipt validation regression tests."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_source_receipt import validate_source_receipt


class TestSourceReceipt(unittest.TestCase):
    def setUp(self):
        self.history = "a" * 64
        self.manifest = "b" * 64
        self.receipt = {
            "schema_version": 1, "issuer": "independent-auditor",
            "issued_at_utc": "2026-10-01T12:00:00Z",
            "history_sha256": self.history,
            "capture_manifest_sha256": self.manifest,
            "model_version": "v1", "reference_id": "receipt-001"
        }

    def _check(self, receipt=None):
        return validate_source_receipt(
            self.receipt if receipt is None else receipt,
            expected_history_sha256=self.history,
            expected_manifest_sha256=self.manifest,
            expected_model_version="v1")

    def test_consistent_receipt_is_not_authentication(self):
        result = self._check()
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertFalse(result["issuer_identity_verified"])
        self.assertFalse(result["signature_verified"])

    def test_mismatched_digest_holds(self):
        self.assertEqual(self._check({**self.receipt, "history_sha256": "c" * 64})["status"], "HOLD")

    def test_naive_timestamp_holds(self):
        self.assertEqual(self._check({**self.receipt, "issued_at_utc": "2026-10-01T12:00:00"})["status"], "HOLD")

    def test_missing_issuer_holds(self):
        self.assertEqual(self._check({**self.receipt, "issuer": ""})["status"], "HOLD")

    def test_unknown_fields_holds(self):
        self.assertEqual(self._check({**self.receipt, "trusted": True})["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
