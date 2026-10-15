import unittest
from over_under_25 import evaluate,poisson_over25

class OverUnder25Tests(unittest.TestCase):
    def test_poisson(self):
        self.assertAlmostEqual(poisson_over25(2),0.3233235838,places=8)
    def test_missing_model(self):
        self.assertEqual(evaluate([{"fixture_id":"x"}])["candidate_count"],0)
    def test_uncalibrated_never_candidate(self):
        x={"fixture_id":"x","expected_goals":3,"over_odds":2,"under_odds":2,"fresh_odds":True}
        self.assertEqual(evaluate([x])["candidate_count"],0)
    def test_only_total_goals(self):
        x={"fixture_id":"x","expected_goals":3,"over_odds":2,"under_odds":2,"fresh_odds":True,"calibrated":True}
        y=evaluate([x])
        self.assertEqual(y["results"][0]["market"],"TOTAL_GOALS_2.5")
        self.assertEqual(y["production_recommendations"],"DISABLED")
    def test_bad_lambda(self):
        with self.assertRaises(ValueError):
            poisson_over25(float("nan"))

if __name__=="__main__":
    unittest.main()
