import unittest
from ops.private_forecast_snapshot import seal
from ops.private_rfc3161_request import make_request, reject_unverified_response


def snapshot():
    return seal({"fixture_id": "synthetic-1", "model": "poisson",
                 "model_version": "synthetic-v1",
                 "prediction_utc": "2026-01-01T10:00:00Z",
                 "kickoff_utc": "2026-01-01T12:00:00Z",
                 "probabilities": {"H": 0.5, "D": 0.3, "A": 0.2},
                 "production_recommendations": "DISABLED"})


class RFC3161RequestTests(unittest.TestCase):
    def test_der_request_is_reproducible_with_nonce(self):
        snap = snapshot()
        first = make_request(snap, nonce=123456)
        second = make_request(snap, nonce=123456)
        self.assertEqual(first["request_der_hex"], second["request_der_hex"])
        self.assertEqual(first["content_type"], "application/timestamp-query")
        self.assertTrue(bytes.fromhex(first["request_der_hex"]).startswith(b"\x30"))
        self.assertFalse(first["capture_time_independently_attested"])

    def test_invalid_nonce_rejected(self):
        with self.assertRaises(ValueError):
            make_request(snapshot(), nonce=0)
        with self.assertRaises(ValueError):
            make_request(snapshot(), nonce=True)

    def test_modified_snapshot_rejected(self):
        snap = snapshot()
        snap["forecast"]["model_version"] = "changed"
        with self.assertRaises(ValueError):
            make_request(snap)

    def test_response_never_self_verifies(self):
        with self.assertRaisesRegex(ValueError, "NOT_IMPLEMENTED"):
            reject_unverified_response(b"\x30\x00")


if __name__ == "__main__":
    unittest.main()
