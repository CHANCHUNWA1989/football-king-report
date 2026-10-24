"""Signature validation regression tests; synthetic keys are never trusted in production."""
import base64
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_signed_receipt import verify_signed_source_receipt

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
except ImportError:
    Ed25519PrivateKey = None


@unittest.skipUnless(Ed25519PrivateKey is not None, "cryptography not installed")
class TestSignedReceipt(unittest.TestCase):
    def setUp(self):
        private = Ed25519PrivateKey.generate()
        self.public = base64.b64encode(private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)).decode()
        receipt = {"schema_version": 1, "issuer": "synthetic-test",
                   "issued_at_utc": "2026-10-01T00:00:00Z",
                   "history_sha256": "a" * 64,
                   "capture_manifest_sha256": "b" * 64,
                   "model_version": "v1", "reference_id": "synthetic-001"}
        message = json.dumps(receipt, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode()
        self.envelope = {
            "schema_version": 1, "algorithm": "Ed25519",
            "key_id": "test-key", "receipt": receipt,
            "signature_b64": base64.b64encode(private.sign(message)).decode()}

    def _verify(self, envelope=None, key_id="test-key"):
        return verify_signed_source_receipt(
            self.envelope if envelope is None else envelope,
            trusted_key_id=key_id, trusted_public_key_b64=self.public,
            expected_history_sha256="a" * 64,
            expected_manifest_sha256="b" * 64,
            expected_model_version="v1")

    def test_valid_signature_research_only(self):
        result = self._verify()
        self.assertTrue(result["signature_verified"])
        self.assertFalse(result["issuer_identity_verified"])
        self.assertEqual(result["status"], "RESEARCH_ONLY")

    def test_modified_receipt_holds(self):
        altered = {**self.envelope, "receipt": {
            **self.envelope["receipt"], "issuer": "forged"}}
        self.assertEqual(self._verify(altered)["status"], "HOLD")

    def test_wrong_key_id_holds(self):
        self.assertEqual(self._verify(key_id="other-key")["status"], "HOLD")

    def test_invalid_signature_holds(self):
        altered = {**self.envelope, "signature_b64": base64.b64encode(b"0" * 64).decode()}
        self.assertEqual(self._verify(altered)["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
