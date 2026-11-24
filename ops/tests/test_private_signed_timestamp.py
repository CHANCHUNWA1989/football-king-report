import base64
import json
import unittest
from ops.private_forecast_snapshot import seal
from ops.private_signed_timestamp import verify_signed


class SignedTimestampTests(unittest.TestCase):
    def setUp(self):
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives import serialization
        except ImportError:
            self.skipTest("cryptography optional dependency not installed")
        self.key = Ed25519PrivateKey.generate()
        self.public = base64.b64encode(self.key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)).decode()
        self.snapshot = seal({"fixture_id": "synthetic-1", "model": "poisson",
                              "model_version": "synthetic-v1",
                              "prediction_utc": "2026-01-01T10:00:00Z",
                              "kickoff_utc": "2026-01-01T12:00:00Z",
                              "probabilities": {"H": 0.5, "D": 0.3, "A": 0.2},
                              "production_recommendations": "DISABLED"})
        self.receipt = {"sha256": self.snapshot["sha256"],
                        "timestamp_utc": "2026-01-01T10:01:00Z",
                        "authority": "synthetic-signer"}

    def signed(self):
        message = json.dumps(self.receipt, sort_keys=True, separators=(",", ":")).encode()
        return {"algorithm": "Ed25519", "receipt": dict(self.receipt),
                "signature_b64": base64.b64encode(self.key.sign(message)).decode()}

    def test_valid_signature_not_time_authority(self):
        report = verify_signed(self.snapshot, self.signed(), trusted_public_key_b64=self.public)
        self.assertTrue(report["signature_valid"])
        self.assertFalse(report["capture_time_independently_attested"])
        self.assertFalse(report["independent_authority_authenticated"])

    def test_modified_receipt_rejected(self):
        signed = self.signed()
        signed["receipt"]["authority"] = "forged"
        with self.assertRaises(ValueError):
            verify_signed(self.snapshot, signed, trusted_public_key_b64=self.public)

    def test_wrong_public_key_rejected(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        other = Ed25519PrivateKey.generate().public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)
        with self.assertRaises(ValueError):
            verify_signed(self.snapshot, self.signed(),
                          trusted_public_key_b64=base64.b64encode(other).decode())

    def test_post_kickoff_signature_rejected(self):
        self.receipt["timestamp_utc"] = "2026-01-01T13:00:00Z"
        with self.assertRaises(ValueError):
            verify_signed(self.snapshot, self.signed(), trusted_public_key_b64=self.public)


if __name__ == "__main__":
    unittest.main()
