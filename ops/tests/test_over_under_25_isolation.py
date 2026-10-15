import unittest
from over_under_25 import evaluate

class FixtureIsolationTests(unittest.TestCase):
    def test_bad_odds_does_not_abort_batch(self):
        rows=[{"fixture_id":"bad","expected_goals":3,"over_odds":1,"under_odds":2},
              {"fixture_id":"good","expected_goals":3,"over_odds":2,"under_odds":2,
               "calibrated":True,"fresh_odds":True}]
        report=evaluate(rows)
        self.assertEqual(len(report["results"]),2)
        self.assertIn("INVALID_ODDS_INPUT",report["results"][0]["blockers"])
        self.assertEqual(report["results"][1]["status"],"RESEARCH_CANDIDATE")
    def test_bad_expected_goals_does_not_abort_batch(self):
        report=evaluate([{"fixture_id":"bad","expected_goals":True},
                         {"fixture_id":"missing"}])
        self.assertEqual(len(report["results"]),2)
        self.assertEqual(report["results"][0]["blockers"],["INVALID_EXPECTED_GOALS"])
        self.assertEqual(report["results"][1]["blockers"],["MISSING_EXPECTED_GOALS"])

if __name__=="__main__":
    unittest.main()
