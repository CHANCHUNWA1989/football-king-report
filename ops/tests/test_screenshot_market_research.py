import unittest
from ops.screenshot_market_research import analyze


class ScreenshotMarketResearchTests(unittest.TestCase):
    def test_normalization_and_hold(self):
        r = analyze({"decimal_odds": {"home": 2.05, "draw": 2.98, "away": 3.24}})
        self.assertEqual(r["status"], "HOLD")
        self.assertAlmostEqual(sum(r["normalized_market_probabilities"].values()), 1.0, places=3)
        self.assertGreater(r["overround"], 0.1)
        self.assertIsNone(r["score_prediction"])
        self.assertFalse(r["betting_permission"])

    def test_invalid_prices_rejected(self):
        for value in (0, 1, True, None, -1):
            with self.assertRaises(ValueError):
                analyze({"decimal_odds": {"home": value, "draw": 2.98, "away": 3.24}})

    def test_no_fabricated_model_probability(self):
        r = analyze({"decimal_odds": {"home": 2.05, "draw": 2.98, "away": 3.24},
                     "model_probability": {"home": 0.99}})
        self.assertIn("NO_INDEPENDENT_MODEL_PROBABILITIES", r["blockers"])


if __name__ == "__main__":
    unittest.main()
