import unittest
from datetime import datetime, timedelta, timezone
from shadow_four_model_audit import evaluate

BASE = {"fixture_id": "match-1", "sealed_at_utc": "2026-10-12T10:00:00Z",
        "kickoff_utc": "2026-10-12T12:00:00Z",
        "result_verified_at_utc": "2026-10-12T15:00:00Z",
        "result_verified": True, "result": "home",
        "model": [0.6, 0.2, 0.2], "market": [0.4, 0.3, 0.3]}

class FourModelAuditTests(unittest.TestCase):
    def test_empty_is_not_fake_success(self):
        result = evaluate([])
        self.assertEqual(result["valid_fixtures"], 0)
        self.assertIsNone(result["models"]["original"]["accuracy"])

    def test_four_models_share_sample(self):
        result = evaluate([BASE])
        self.assertEqual(result["valid_fixtures"], 1)
        self.assertEqual(len(result["models"]), 4)
        self.assertTrue(all(x["sample_size"] == 1 for x in result["models"].values()))
        self.assertEqual(result["models"]["original"]["accuracy"], 1.0)

    def test_post_kickoff_prediction_excluded(self):
        row = dict(BASE, sealed_at_utc="2026-10-12T13:00:00Z")
        self.assertEqual(evaluate([row])["valid_fixtures"], 0)

    def test_unverified_excluded(self):
        self.assertEqual(evaluate([dict(BASE, result_verified=False)])["valid_fixtures"], 0)

    def test_duplicate_not_double_counted(self):
        self.assertEqual(evaluate([BASE, BASE])["valid_fixtures"], 1)

    def test_conflicting_duplicate_quarantined(self):
        self.assertEqual(evaluate([BASE, dict(BASE, result="away")])["valid_fixtures"], 0)

    def test_invalid_probability_excluded(self):
        self.assertEqual(evaluate([dict(BASE, model=[0.9, 0.9, -0.8])])["valid_fixtures"], 0)

if __name__ == "__main__":
    unittest.main()
