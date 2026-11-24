import copy
import unittest
from ops.private_forecast_snapshot import seal, verify


def forecast():
    return {"fixture_id": "synthetic-1", "model": "poisson", "model_version": "test-v1",
            "prediction_utc": "2026-01-01T10:00:00Z",
            "kickoff_utc": "2026-01-01T12:00:00Z",
            "probabilities": {"H": 0.5, "D": 0.3, "A": 0.2},
            "production_recommendations": "DISABLED"}


class SnapshotTests(unittest.TestCase):
    def test_deterministic_seal(self):
        first = seal(forecast())
        second = seal(copy.deepcopy(forecast()))
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertTrue(verify(first))
        self.assertFalse(first["capture_time_independently_attested"])

    def test_probability_tampering_rejected(self):
        snap = seal(forecast())
        snap["forecast"]["probabilities"] = {"H": 0.6, "D": 0.2, "A": 0.2}
        with self.assertRaises(ValueError):
            verify(snap)

    def test_future_prediction_rejected(self):
        row = forecast()
        row["prediction_utc"] = "2026-01-01T13:00:00Z"
        with self.assertRaises(ValueError):
            seal(row)

    def test_provenance_self_promotion_rejected(self):
        snap = seal(forecast())
        snap["capture_time_independently_attested"] = True
        with self.assertRaises(ValueError):
            verify(snap)

    def test_model_promotion_rejected(self):
        row = forecast()
        row["production_recommendations"] = "ENABLED"
        with self.assertRaises(ValueError):
            seal(row)


if __name__ == "__main__":
    unittest.main()
