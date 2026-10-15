import unittest
from value_research_pipeline import evaluate

class ValueResearchTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(evaluate([])["candidate_count"],0)
    def test_missing_evidence(self):
        report=evaluate([{"fixture_id":"1","market":"over_2_5"}])
        self.assertEqual(report["candidate_count"],0)
    def test_negative_ev(self):
        report=evaluate([{"odds":1.3,"probability":0.75,"calibrated":True,"fresh_odds":True}])
        self.assertEqual(report["candidate_count"],0)
    def test_unverified_model(self):
        report=evaluate([{"odds":2.1,"probability":0.6,"fresh_odds":True}])
        self.assertEqual(report["candidate_count"],0)
    def test_positive_candidate_not_production(self):
        report=evaluate([{"odds":2.1,"probability":0.55,"calibrated":True,"fresh_odds":True}])
        self.assertEqual(report["candidate_count"],1)
        self.assertEqual(report["production_recommendations"],"DISABLED")

if __name__=="__main__":
    unittest.main()
