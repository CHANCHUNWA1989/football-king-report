"""Tests for structured research admission report."""
import hashlib
import base64
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_admission_report import build_pinned_admission_report


class TestAdmissionReport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        folder = Path(self.tmp.name)
        self.history = folder / "history.json"
        self.manifest = folder / "captures.json"
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        rows, captures = [], []
        for i in range(180):
            kickoff = base + timedelta(days=i)
            predicted = (kickoff - timedelta(hours=2)).isoformat()
            rows.append({"event_id": f"m{i}", "model_version": "v1",
                         "predicted_at_utc": predicted,
                         "kickoff_at_utc": kickoff.isoformat(),
                         "settled_at_utc": (kickoff + timedelta(hours=3)).isoformat(),
                         "probability": 0.8, "outcome": 1})
            captures.append({"event_id": f"m{i}",
                             "captured_at_utc": predicted,
                             "evidence_source": "test-ledger"})
        raw = json.dumps({"schema_version": 1, "model_version": "v1",
                          "rows": rows}).encode()
        self.history.write_bytes(raw)
        self.history_digest = hashlib.sha256(raw).hexdigest()
        raw = json.dumps({"schema_version": 1,
                          "history_sha256": self.history_digest,
                          "captures": captures}).encode()
        self.manifest.write_bytes(raw)
        self.manifest_digest = hashlib.sha256(raw).hexdigest()
        self.private = Ed25519PrivateKey.generate()
        self.public_b64 = base64.b64encode(self.private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)).decode()

    def _receipt(self):
        return {"schema_version": 1, "issuer": "test-issuer",
                "issued_at_utc": "2026-10-01T00:00:00Z",
                "history_sha256": self.history_digest,
                "capture_manifest_sha256": self.manifest_digest,
                "model_version": "v1", "reference_id": "test-001"}

    def _signed(self):
        receipt = self._receipt()
        message = json.dumps(receipt, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode()
        return {"schema_version": 1, "algorithm": "Ed25519",
                "key_id": "test-key", "receipt": receipt,
                "signature_b64": base64.b64encode(self.private.sign(message)).decode()}

    def _report(self, manifest_digest=None):
        return build_pinned_admission_report(
            self.history, expected_sha256=self.history_digest,
            expected_model_version="v1", manifest_path=self.manifest,
            expected_manifest_sha256=manifest_digest or self.manifest_digest,
            source_receipt=self._signed(), trusted_key_id="test-key",
            trusted_public_key_b64=self.public_b64)

    def test_passed_report_is_research_only(self):
        report = self._report()
        self.assertEqual(report["status"], "RESEARCH_ONLY")
        self.assertEqual(report["checks"]["capture_manifest"], "PASS")
        self.assertEqual(report["capture_event_count"], 180)
        self.assertEqual(report["checks"]["trusted_timestamp_authority"], "NOT_VERIFIED")
        self.assertEqual(report["checks"]["receipt_signature"], "PASS")
        self.assertEqual(report["checks"]["issuer_identity"], "NOT_VERIFIED")
        self.assertEqual(report["checks"]["production_admission"], "BLOCKED")
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_missing_receipt_holds(self):
        report = build_pinned_admission_report(
            self.history, expected_sha256=self.history_digest,
            expected_model_version="v1", manifest_path=self.manifest,
            expected_manifest_sha256=self.manifest_digest)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["checks"]["source_receipt_consistency"], "FAIL")
        self.assertEqual(report["checks"]["walkforward"], "PASS")

    def test_failed_manifest_report_holds(self):
        report = self._report("0" * 64)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["checks"]["capture_manifest"], "NOT_VERIFIED")
        self.assertIn("evidence_reason", report["failure"])


if __name__ == "__main__":
    unittest.main()
