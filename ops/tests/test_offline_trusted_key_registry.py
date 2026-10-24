"""Pinned key registry fail-closed regression tests."""
import base64
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_trusted_key_registry import load_trusted_key_registry


class TestTrustedKeyRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "keys.json"
        self.document = {"schema_version": 1, "keys": [{
            "key_id": "auditor-2026", "algorithm": "Ed25519",
            "public_key_b64": base64.b64encode(b"a" * 32).decode(),
            "status": "active"}]}
        self._write()

    def _write(self):
        raw = json.dumps(self.document).encode()
        self.path.write_bytes(raw)
        self.digest = hashlib.sha256(raw).hexdigest()

    def _load(self, digest=None):
        return load_trusted_key_registry(
            self.path, expected_sha256=digest or self.digest,
            key_id="auditor-2026")

    def test_active_key_is_research_only(self):
        result = self._load()
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertFalse(result["issuer_identity_verified"])

    def test_revoked_key_holds(self):
        self.document["keys"][0]["status"] = "revoked"
        self._write()
        self.assertEqual(self._load()["status"], "HOLD")

    def test_digest_mismatch_holds(self):
        self.assertEqual(self._load("0" * 64)["status"], "HOLD")

    def test_duplicate_ids_holds(self):
        self.document["keys"].append(dict(self.document["keys"][0]))
        self._write()
        self.assertEqual(self._load()["status"], "HOLD")

    def test_duplicate_json_field_holds(self):
        raw = b'{"schema_version":1,"schema_version":1,"keys":[]}'
        self.path.write_bytes(raw)
        self.digest = hashlib.sha256(raw).hexdigest()
        self.assertEqual(self._load()["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
