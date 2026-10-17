import unittest
from shared.recommendation_screen import screen_recommendation

class ScreenTests(unittest.TestCase):
    def test_unverified_market_never_qualifies(self):
        r = screen_recommendation("football", .6, 2.0, verified_model=True, sample_size=200)
        self.assertFalse(r["research_candidate"])
        self.assertFalse(r["live_execution_allowed"])
    def test_research_candidate_not_live_order(self):
        r = screen_recommendation("basketball", .6, 2.0, verified_market_data=True, verified_model=True, sample_size=200)
        self.assertTrue(r["research_candidate"])
        self.assertFalse(r["live_execution_allowed"])
        self.assertAlmostEqual(r["estimated_ev"], .2)
    def test_quant_requires_cost_risk_review(self):
        r = screen_recommendation("quant", .6, verified_market_data=True, verified_model=True, sample_size=200)
        self.assertFalse(r["research_candidate"])
    def test_small_sample_holds(self):
        self.assertIn("INSUFFICIENT_SAMPLE", screen_recommendation("football", .6, 2, verified_market_data=True, verified_model=True)["reasons"])
    def test_invalid_probability(self):
        with self.assertRaises(ValueError):
            screen_recommendation("football", float("nan"), 2)
    def test_invalid_odds(self):
        with self.assertRaises(ValueError):
            screen_recommendation("football", .6, float("inf"))
    def test_below_ev_threshold(self):
        self.assertIn("EV_BELOW_RESEARCH_THRESHOLD", screen_recommendation("football", .5, 2, verified_market_data=True, verified_model=True, sample_size=200)["reasons"])

if __name__ == "__main__":
    unittest.main()
