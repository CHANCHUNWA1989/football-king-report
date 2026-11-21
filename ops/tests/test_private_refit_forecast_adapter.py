import copy
import unittest
from datetime import datetime, timedelta, timezone
from ops.private_refit_forecast_adapter import adapt


class RefitAdapterTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
        self.row = {
            "fixture_id": "event-1",
            "kickoff_utc": (self.now + timedelta(hours=2)).isoformat(),
            "as_of_utc": (self.now - timedelta(minutes=30)).isoformat(),
            "model_id": "penaltyblog-poisson-offline-challenger-v1",
            "training_match_count": 45,
            "probabilities": [.45, .3, .25],
            "source_authenticity_verified": False,
            "independently_timestamped": False,
        }
        self.report = {
            "status": "HOLD",
            "reason": "PROSPECTIVE_SOURCE_AND_RESULT_ATTESTATION_MISSING",
            "production_recommendations": "DISABLED",
            "positive_ev_verified": False,
            "independent_provenance_verified": False,
            "refit_count": 1,
            "predictions": [self.row],
        }

    def test_valid_offline_refit_converts_without_certification(self):
        result = adapt(self.report, now=self.now)
        self.assertEqual(result[0]["probabilities"], {"H": .45, "D": .3, "A": .25})
        self.assertFalse(result[0]["independently_timestamped"])

    def test_bad_probability_rejected(self):
        x = copy.deepcopy(self.report)
        x["predictions"][0]["probabilities"][0] = .95
        with self.assertRaises(ValueError):
            adapt(x, now=self.now)

    def test_post_kickoff_rejected(self):
        x = copy.deepcopy(self.report)
        x["predictions"][0]["kickoff_utc"] = (self.now - timedelta(minutes=1)).isoformat()
        with self.assertRaises(ValueError):
            adapt(x, now=self.now)

    def test_self_certified_rejected(self):
        x = copy.deepcopy(self.report)
        x["predictions"][0]["source_authenticity_verified"] = True
        with self.assertRaises(ValueError):
            adapt(x, now=self.now)

    def test_duplicate_rejected(self):
        x = copy.deepcopy(self.report)
        x["predictions"].append(copy.deepcopy(self.row))
        x["refit_count"] = 2
        with self.assertRaises(ValueError):
            adapt(x, now=self.now)

    def test_bad_report_rejected(self):
        x = copy.deepcopy(self.report)
        x["positive_ev_verified"] = True
        with self.assertRaises(ValueError):
            adapt(x, now=self.now)


if __name__ == "__main__":
    unittest.main()
