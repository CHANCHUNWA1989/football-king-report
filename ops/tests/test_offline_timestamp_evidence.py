"""Synthetic timestamp evidence integrity tests."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_timestamp_evidence import validate_timestamp_evidence


class TestTimestampEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "timestamp.json"
        self.evidence = {
            "schema_version": 1, "authority": "synthetic-audit",
            "observed_at_utc": "2026-10-01T12:00:00Z",
            "history_sha256": "a" * 64, "capture_manifest_sha256": "b" * 64,
            "reference_id": "test-001"}
        self._write()

    def _write(self):
        raw = json.dumps(self.evidence).encode()
        self.path.write_bytes(raw)
        self.digest = hashlib.sha256(raw).hexdigest()

    def _check(self, digest=None):
        return validate_timestamp_evidence(
            self.path, expected_sha256=digest or self.digest,
            expected_history_sha256="a" * 64,
            expected_manifest_sha256="b" * 64)

    def test_pinned_evidence_is_research_only(self):
        result = self._check()
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertFalse(result["trusted_timestamp_authority_verified"])

    def test_modified_digest_holds(self):
        self.assertEqual(self._check("0" * 64)["status"], "HOLD")

    def test_wrong_history_holds(self):
        self.evidence["history_sha256"] = "c" * 64
        self._write()
        self.assertEqual(self._check()["status"], "HOLD")

    def test_naive_timestamp_holds(self):
        self.evidence["observed_at_utc"] = "2026-10-01T12:00:00"
        self._write()
        self.assertEqual(self._check()["status"], "HOLD")

    def test_duplicate_field_holds(self):
        raw = b'{"schema_version":1,"schema_version":1}'
        self.path.write_bytes(raw)
        self.digest = hashlib.sha256(raw).hexdigest()
        self.assertEqual(self._check()["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
