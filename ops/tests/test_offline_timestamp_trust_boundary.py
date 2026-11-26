"""Research-only timestamp trust boundary regression tests.

Integrity-only RFC3161 token placeholders must never imply cryptographic TSA
verification or authorize production recommendations.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_admission_report import build_pinned_admission_report


class TestTimestampTrustBoundary(unittest.TestCase):
    def test_missing_inputs_cannot_claim_tsa_trust(self):
        report = build_pinned_admission_report(
            "/nonexistent/history.json",
            expected_sha256="a" * 64,
            expected_model_version="v1",
            manifest_path="/nonexistent/manifest.json",
            expected_manifest_sha256="b" * 64)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["checks"]["trusted_timestamp_authority"], "NOT_INDEPENDENTLY_VERIFIED")
        self.assertEqual(report["checks"]["rfc3161_signature_verification"], "FAIL")
        self.assertEqual(report["checks"]["rfc3161_certificate_chain"], "NOT_VERIFIED")
        self.assertEqual(report["checks"]["rfc3161_message_imprint"], "NOT_VERIFIED")
        self.assertEqual(report["checks"]["prematch_capture_independence"], "NOT_VERIFIED")
        self.assertEqual(report["checks"]["production_admission"], "BLOCKED")
        self.assertEqual(report["production_recommendations"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
