"""Tests for structured research admission report."""
import hashlib
import base64
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
except ImportError:
    Ed25519PrivateKey = None
    serialization = None

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_admission_report import build_pinned_admission_report


@unittest.skipUnless(Ed25519PrivateKey is not None, "cryptography unavailable; verified in pinned research CI")
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
        self.registry = folder / "registry.json"
        self._write_registry()
        self.timestamp_path = folder / "timestamp.json"
        self._write_timestamp()
        self.attestation_path = folder / "attestation.json"
        self._write_attestation()

    def _write_registry(self, status="active"):
        raw = json.dumps({"schema_version": 1, "keys": [{
            "key_id": "test-key", "algorithm": "Ed25519",
            "public_key_b64": self.public_b64, "status": status}]}).encode()
        self.registry.write_bytes(raw)
        self.registry_digest = hashlib.sha256(raw).hexdigest()

    def _write_timestamp(self):
        raw = json.dumps({"schema_version": 1, "authority": "synthetic-audit",
            "observed_at_utc": "2026-10-01T12:00:00Z",
            "history_sha256": self.history_digest,
            "capture_manifest_sha256": self.manifest_digest,
            "reference_id": "synthetic-time-001"}).encode()
        self.timestamp_path.write_bytes(raw)
        self.timestamp_digest = hashlib.sha256(raw).hexdigest()

    def _write_attestation(self):
        raw = json.dumps({"schema_version": 1, "format": "RFC3161_DER",
            "timestamp_token_b64": base64.b64encode(bytes([0x30, 0x46, 0x04, 0x44]) + b"x" * 68).decode(),
            "evidence_sha256": self.timestamp_digest}).encode()
        self.attestation_path.write_bytes(raw)
        self.attestation_digest = hashlib.sha256(raw).hexdigest()

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
            trusted_registry_path=self.registry,
            trusted_registry_sha256=self.registry_digest,
            timestamp_evidence_path=self.timestamp_path,
            timestamp_evidence_sha256=self.timestamp_digest,
            timestamp_attestation_path=self.attestation_path,
            timestamp_attestation_sha256=self.attestation_digest)

    def test_unsigned_synthetic_timestamp_cannot_be_admitted(self):
        report = self._report()
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["reason"], "UNVERIFIED_RFC3161_TIMESTAMP")
        self.assertEqual(report["checks"]["rfc3161_signature_verification"], "FAIL")
        self.assertEqual(report["checks"]["capture_manifest"], "PASS")
        self.assertEqual(report["capture_event_count"], 180)
        self.assertEqual(report["checks"]["trusted_timestamp_authority"], "NOT_INDEPENDENTLY_VERIFIED")
        self.assertEqual(report["checks"]["tsa_operator_identity"], "NOT_INDEPENDENTLY_VERIFIED")
        self.assertEqual(report["checks"]["receipt_signature"], "PASS")
        self.assertEqual(report["checks"]["timestamp_evidence_integrity"], "PASS")
        self.assertEqual(report["checks"]["timestamp_attestation_integrity"], "PASS")
        self.assertEqual(report["checks"]["issuer_identity"], "NOT_VERIFIED")
        self.assertEqual(report["checks"]["production_admission"], "BLOCKED")
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_signature_without_verified_tsa_chain_holds(self):
        """Research admission must reject a signature-only verification claim."""
        with patch("offline_admission_report.verify_rfc3161_token",
                   return_value={
                       "rfc3161_signature_verified": True,
                       "tsa_certificate_chain_verified": False,
                       "reason": "TEST_CHAIN_UNVERIFIED",
                   }):
            report = self._report()
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["checks"]["rfc3161_signature_verification"], "FAIL")
        self.assertEqual(report["checks"]["production_admission"], "BLOCKED")

    def test_missing_timestamp_attestation_holds(self):
        self.attestation_path.unlink()
        report = self._report()
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["checks"]["timestamp_attestation_integrity"], "FAIL")

    def test_missing_timestamp_evidence_holds(self):
        self.timestamp_path.unlink()
        report = self._report()
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["checks"]["timestamp_evidence_integrity"], "FAIL")

    def test_revoked_registry_key_holds(self):
        self._write_registry("revoked")
        report = self._report()
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["checks"]["trusted_key_registry"], "FAIL")

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
