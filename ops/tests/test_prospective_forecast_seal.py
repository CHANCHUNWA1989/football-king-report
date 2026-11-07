import unittest
from datetime import datetime, timezone
from ops.prospective_forecast_seal import seal


def sample():
    return {"schema": "football-king-forecast-seal-input-v1",
            "source_namespace": "synthetic", "fixture_id": "game-1",
            "kickoff_utc": "2026-11-08T20:00:00+00:00",
            "as_of_utc": "2026-11-08T18:00:00+00:00",
            "model_id": "synthetic-poisson", "model_version": "v1",
            "probabilities": [.5, .3, .2], "production_recommendations": "DISABLED"}


NOW = datetime(2026, 11, 8, 19, tzinfo=timezone.utc)


class SealTests(unittest.TestCase):
    def test_seals_research_only(self):
        result = seal(sample(), now=NOW)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertFalse(result["independently_timestamped"])
        self.assertEqual(len(result["payload_sha256"]), 64)

    def test_deterministic_hash(self):
        self.assertEqual(seal(sample(), now=NOW)["payload_sha256"],
                         seal(sample(), now=NOW)["payload_sha256"])

    def test_post_kickoff_rejected(self):
        with self.assertRaises(ValueError):
            seal(sample(), now=datetime(2026, 11, 8, 21, tzinfo=timezone.utc))

    def test_future_as_of_rejected(self):
        p = sample()
        p["as_of_utc"] = "2026-11-08T19:30:00+00:00"
        with self.assertRaises(ValueError):
            seal(p, now=NOW)

    def test_invalid_probabilities_rejected(self):
        p = sample()
        p["probabilities"] = [.9, .9, -.8]
        with self.assertRaises(ValueError):
            seal(p, now=NOW)

    def test_production_rejected(self):
        p = sample()
        p["production_recommendations"] = "ENABLED"
        with self.assertRaises(ValueError):
            seal(p, now=NOW)


if __name__ == "__main__":
    unittest.main()
