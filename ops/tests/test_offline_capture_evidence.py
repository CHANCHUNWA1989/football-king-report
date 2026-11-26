"""Synthetic independent capture claim checks."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_capture_evidence import assess_external_capture_evidence


class TestCaptureEvidence(unittest.TestCase):
    def setUp(self):
        self.digest = "a" * 64
        self.rows = [
            {"predicted_at_utc": "2026-01-01T09:00:00Z",
             "kickoff_at_utc": "2026-01-01T12:00:00Z"},
            {"predicted_at_utc": "2026-01-01T09:30:00Z",
             "kickoff_at_utc": "2026-01-01T14:00:00Z"},
        ]

    def _check(self, **overrides):
        args = dict(rows=self.rows, history_sha256=self.digest,
                    evidence_sha256=self.digest,
                    captured_at_utc="2026-01-01T10:00:00Z",
                    evidence_source="independent-capture-record")
        args.update(overrides)
        return assess_external_capture_evidence(**args)

    def test_consistent_claim_still_unverified(self):
        result = self._check()
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertFalse(result["timestamp_authority_verified"])

    def test_digest_mismatch_holds(self):
        self.assertEqual(self._check(evidence_sha256="b" * 64)["status"], "HOLD")

    def test_capture_after_kickoff_holds(self):
        self.assertEqual(
            self._check(captured_at_utc="2026-01-01T12:01:00Z")["status"], "HOLD")

    def test_capture_before_prediction_holds(self):
        self.assertEqual(
            self._check(captured_at_utc="2026-01-01T08:00:00Z")["status"], "HOLD")

    def test_missing_source_holds(self):
        self.assertEqual(self._check(evidence_source="")["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
