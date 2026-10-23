"""Synthetic third-party timestamp token preflight tests."""
import base64
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_timestamp_attestation import inspect_timestamp_attestation


class TestTimestampAttestation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "attestation.json"
        self.data = {
            "schema_version": 1, "format": "RFC3161_DER",
            "timestamp_token_b64": base64.b64encode(b"not-a-real-tsa-token" * 4).decode(),
            "evidence_sha256": "a" * 64}
        self._write()

    def _write(self):
        raw = json.dumps(self.data).encode()
        self.path.write_bytes(raw)
        self.digest = hashlib.sha256(raw).hexdigest()

    def _check(self, digest=None):
        return inspect_timestamp_attestation(
            self.path, expected_sha256=digest or self.digest,
            expected_evidence_sha256="a" * 64)

    def test_pinned_token_is_not_trusted_timestamp(self):
        result = self._check()
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertFalse(result["trusted_timestamp_authority_verified"])
        self.assertEqual(result["attestation_integrity"], "PASS")

    def test_tampered_file_holds(self):
        self.assertEqual(self._check("0" * 64)["status"], "HOLD")

    def test_mismatched_evidence_holds(self):
        self.data["evidence_sha256"] = "b" * 64
        self._write()
        self.assertEqual(self._check()["status"], "HOLD")

    def test_bad_base64_holds(self):
        self.data["timestamp_token_b64"] = "!"
        self._write()
        self.assertEqual(self._check()["status"], "HOLD")

    def test_boolean_schema_holds(self):
        self.data["schema_version"] = True
        self._write()
        self.assertEqual(self._check()["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
