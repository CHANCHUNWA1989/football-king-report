import base64
import json
import unittest
from ops.private_forecast_snapshot import seal
from ops.private_historical_key_verification import verify_historical


class HistoricalKeyTests(unittest.TestCase):
    def setUp(self):
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives import serialization
        except ImportError:
            self.skipTest("cryptography optional dependency not installed")
        self.key = Ed25519PrivateKey.generate()
        public = self.key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        self.snapshot = seal({"fixture_id": "synthetic-1", "model": "poisson",
                              "model_version": "synthetic-v1",
                              "prediction_utc": "2026-01-01T10:00:00Z",
                              "kickoff_utc": "2026-01-01T12:00:00Z",
                              "probabilities": {"H": 0.5, "D": 0.3, "A": 0.2},
                              "production_recommendations": "DISABLED"})
        receipt = {"sha256": self.snapshot["sha256"], "timestamp_utc": "2026-01-01T10:01:00Z",
                   "authority": "synthetic-authority"}
        message = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
        self.signed = {"algorithm": "Ed25519", "receipt": receipt,
                       "signature_b64": base64.b64encode(self.key.sign(message)).decode()}
        self.anchor = {"authority": "synthetic-authority", "public_key_b64": base64.b64encode(public).decode(),
                       "valid_from_utc": "2025-01-01T00:00:00Z",
                       "valid_until_utc": "2026-02-01T00:00:00Z", "revoked": False}
        self.policy = {"schema": "research-trust-policy-v1", "anchors": [self.anchor]}

    def verify(self, **kwargs):
        return verify_historical(self.snapshot, self.signed, self.policy,
                                 verification_time_utc="2026-11-01T00:00:00Z", **kwargs)

    def test_expired_now_but_valid_at_claimed_time_not_attested(self):
        result = self.verify()
        self.assertTrue(result["historical_key_window_matches_claimed_time"])
        self.assertFalse(result["historical_signing_time_independently_verified"])
        self.assertFalse(result["capture_time_independently_attested"])

    def test_revoked_key_rejected_even_for_old_receipt(self):
        self.anchor["revoked"] = True
        with self.assertRaises(ValueError):
            self.verify()

    def test_outside_historical_window_rejected(self):
        self.anchor["valid_until_utc"] = "2025-12-01T00:00:00Z"
        with self.assertRaises(ValueError):
            self.verify()

    def test_self_claimed_external_time_rejected(self):
        with self.assertRaises(ValueError):
            self.verify(externally_authenticated_signing_time_utc="2026-01-01T10:01:00Z")

    def test_future_receipt_rejected(self):
        with self.assertRaises(ValueError):
            verify_historical(self.snapshot, self.signed, self.policy,
                              verification_time_utc="2025-12-01T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
