import unittest
from over_under_25 import evaluate

class MarketDivergenceGuardTests(unittest.TestCase):
    def test_screenshot_style_large_divergence_is_hold(self):
        result=evaluate([{"fixture_id":"example","expected_goals":2.47,
            "over_odds":1.43,"under_odds":2.60,
            "calibrated":True,"fresh_odds":True}])["results"][0]
        self.assertEqual(result["status"],"HOLD")
        self.assertNotIn("side",result)
        self.assertIn("MODEL_MARKET_DIVERGENCE_UNVERIFIED",result["blockers"])
        self.assertGreater(result["model_market_divergence"],0.15)
        self.assertEqual(result["production_recommendations"],"DISABLED")
    def test_close_market_does_not_trigger_guard(self):
        result=evaluate([{"fixture_id":"example","expected_goals":2.47,
            "over_odds":2.0,"under_odds":2.0,
            "calibrated":True,"fresh_odds":True}])["results"][0]
        self.assertNotIn("MODEL_MARKET_DIVERGENCE_UNVERIFIED",result.get("blockers",[]))

if __name__=="__main__":
    unittest.main()
