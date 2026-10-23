"""Negative RFC3161 cryptographic verification tests."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_rfc3161_verify import verify_rfc3161_token


class TestRFC3161Verification(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.token = root / "token.der"
        self.evidence = root / "evidence.json"
        self.ca = root / "tsa-ca.pem"
        self.token.write_bytes(b"not-a-valid-rfc3161-token")
        self.evidence.write_bytes(b"example-evidence")
        self.ca.write_bytes(b"not-a-real-ca")
        self.digest = hashlib.sha256(self.ca.read_bytes()).hexdigest()
        self.token_digest = hashlib.sha256(self.token.read_bytes()).hexdigest()

    def _check(self, digest=None):
        return verify_rfc3161_token(
            token_path=self.token, evidence_path=self.evidence,
            ca_bundle_path=self.ca,
            expected_ca_bundle_sha256=digest or self.digest,
            expected_token_sha256=self.token_digest)

    def test_invalid_token_holds(self):
        result = self._check()
        self.assertEqual(result["status"], "HOLD")
        self.assertFalse(result["trusted_timestamp_authority_verified"])

    def test_mismatched_attested_token_holds(self):
        self.token.write_bytes(b"a-different-token")
        self.assertEqual(self._check()["status"], "HOLD")

    def test_wrong_ca_digest_holds(self):
        self.assertEqual(self._check("0" * 64)["status"], "HOLD")

    def test_missing_token_holds(self):
        self.token.unlink()
        self.assertEqual(self._check()["status"], "HOLD")

    def test_missing_ca_holds(self):
        self.ca.unlink()
        self.assertEqual(self._check()["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
