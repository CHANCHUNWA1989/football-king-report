import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge_shadow_forecasts import convert


def fixture():
    return {"schema": "football-king-uncalibrated-shadow-1",
            "status": "SHADOW_ONLY", "as_of_utc": "2026-10-15T10:00:00Z",
            "predictions_count": 1, "production_recommendations": "DISABLED",
            "predictions": [{
                "event_id": "e1", "prediction_utc": "2026-10-15T10:00:00Z",
                "kickoff_utc": "2026-10-15T12:00:00Z",
                "model": "poisson-shrinkage-unvalidated-v4.1", "calibrated": False,
                "p_home": 0.5, "p_draw": 0.3, "p_away": 0.2,
                "production_recommendations": "DISABLED"}]}


class BridgeTests(unittest.TestCase):
    def test_valid_shadow_is_only_research_forecast(self):
        rows = convert(fixture())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "football-king-poisson-shrinkage-v4.1")
        self.assertFalse(rows[0]["independently_verified"])
        self.assertEqual(rows[0]["forecast_utc"], "2026-10-15T10:00:00Z")

    def test_no_post_kickoff_predictions(self):
        data = fixture()
        data["predictions"][0]["kickoff_utc"] = "2026-10-15T09:00:00Z"
        with self.assertRaises(ValueError):
            convert(data)

    def test_no_consensus_or_changed_model(self):
        data = fixture()
        data["predictions"][0]["model"] = "market-no-vig"
        with self.assertRaises(ValueError):
            convert(data)

    def test_no_count_mismatch(self):
        data = fixture()
        data["predictions_count"] = 2
        with self.assertRaises(ValueError):
            convert(data)


if __name__ == "__main__":
    unittest.main()
