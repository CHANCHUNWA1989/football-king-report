"""Synthetic temporal leakage tests for uncalibrated research forecasts."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shadow_forecast import poisson_1x2, predict_league, generate


class ShadowForecastTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 9, 4, 0, tzinfo=timezone.utc)
        self.history = []
        teams = ["A", "B", "C", "D", "E", "F"]
        for i in range(48):
            self.history.append({
                "date": (self.now - timedelta(days=i + 1)).date().isoformat(),
                "home": teams[i % 6], "away": teams[(i + 1) % 6],
                "score_ft": [1 + (i % 2), (i % 3 == 0) * 1],
                "status": "FINISHED", "kickoff_utc": None
            })
        self.future = {
            "date": "2026-10-10", "home": "A", "away": "B",
            "kickoff_utc": "2026-10-10T12:00:00+00:00",
            "event_id": "fixture123", "score_ft": None, "status": "SCHEDULED",
        }

    def test_future_predictions_exclude_filled_results(self):
        rows = self.history + [{**self.future, "score_ft": [9, 0]}]
        self.assertEqual(predict_league(rows, "epl", self.now), [])

    def test_future_probability_is_normalized_and_uncalibrated(self):
        result = predict_league(self.history + [self.future], "epl", self.now)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(sum(result[0][k] for k in ("p_home", "p_draw", "p_away")), 1, places=6)
        self.assertFalse(result[0]["calibrated"])
        self.assertEqual(result[0]["production_recommendations"], "DISABLED")

    def test_unknown_kickoff_excluded(self):
        self.assertEqual(predict_league(self.history + [{**self.future, "kickoff_utc": None}], "epl", self.now), [])

    def test_same_day_result_not_used_for_training(self):
        data = [{**row, "date": "2026-10-09"} for row in self.history] + [self.future]
        self.assertEqual(predict_league(data, "epl", self.now), [])

    def test_need_sufficient_history(self):
        self.assertEqual(predict_league(self.history[:4] + [self.future], "epl", self.now), [])

    def test_future_probabilities_never_prove_profitability(self):
        p = poisson_1x2(1.3, 1.1)
        self.assertAlmostEqual(sum(p), 1, places=6)
        with self.assertRaises(ValueError):
            poisson_1x2(40, 1.2)

    def test_network_failure_stays_hold(self):
        def getter(**kwargs):
            return {"status": "HOLD", "reason": "NO_NETWORK", "matches": []}
        result = generate(now=self.now, getter=getter)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["predictions_count"], 0)


if __name__ == "__main__":
    unittest.main()
