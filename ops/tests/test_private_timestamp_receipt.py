import unittest
from ops.private_forecast_snapshot import seal
from ops.private_timestamp_receipt import check


def fixture():
    snapshot = seal({"fixture_id": "synthetic-1", "model": "poisson",
                     "model_version": "synthetic-v1",
                     "prediction_utc": "2026-01-01T10:00:00Z",
                     "kickoff_utc": "2026-01-01T12:00:00Z",
                     "probabilities": {"H": 0.5, "D": 0.3, "A": 0.2},
                     "production_recommendations": "DISABLED"})
    return snapshot, {"sha256": snapshot["sha256"],
                      "timestamp_utc": "2026-01-01T10:01:00Z",
                      "authority": "synthetic-authority"}


class TimestampReceiptTests(unittest.TestCase):
    def test_receipt_without_trust_is_unverified(self):
        snapshot, receipt = fixture()
        report = check(snapshot, receipt)
        self.assertTrue(report["receipt_consistent"])
        self.assertFalse(report["capture_time_independently_attested"])
        self.assertFalse(report["trusted_reference_matched"])

    def test_matching_reference_does_not_self_certify_authority(self):
        snapshot, receipt = fixture()
        report = check(snapshot, receipt, trusted_digest=snapshot["sha256"],
                       trusted_timestamp=receipt["timestamp_utc"])
        self.assertTrue(report["trusted_reference_matched"])
        self.assertFalse(report["independent_authority_authenticated"])

    def test_mismatched_digest_rejected(self):
        snapshot, receipt = fixture()
        receipt["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            check(snapshot, receipt)

    def test_post_kickoff_receipt_rejected(self):
        snapshot, receipt = fixture()
        receipt["timestamp_utc"] = "2026-01-01T12:00:00Z"
        with self.assertRaises(ValueError):
            check(snapshot, receipt)

    def test_forged_provenance_field_rejected(self):
        snapshot, receipt = fixture()
        receipt["verified"] = True
        with self.assertRaises(ValueError):
            check(snapshot, receipt)


if __name__ == "__main__":
    unittest.main()
