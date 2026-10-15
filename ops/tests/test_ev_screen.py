import unittest
from ev_screen import screen_ev

class EVScreenTests(unittest.TestCase):
    def test_low_odds_without_edge(self):
        result=screen_ev(1.3,0.75,calibrated=True,fresh_odds=True)
        self.assertFalse(result["research_candidate"])
        self.assertAlmostEqual(result["ev"],-0.025)
    def test_uncalibrated_stays_blocked(self):
        result=screen_ev(2.1,0.55,fresh_odds=True)
        self.assertIn("UNCALIBRATED_PROBABILITY",result["blockers"])
    def test_valid_research_candidate_still_not_production(self):
        result=screen_ev(2.1,0.55,calibrated=True,fresh_odds=True)
        self.assertTrue(result["research_candidate"])
        self.assertEqual(result["production_recommendations"],"DISABLED")
    def test_invalid_odds(self):
        with self.assertRaises(ValueError):screen_ev(1,0.6)

if __name__=="__main__":
    unittest.main()
