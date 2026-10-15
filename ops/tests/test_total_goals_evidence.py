import unittest
from total_goals_evidence import assess

NOW="2026-10-15T12:00:00Z"
BASE={"fixture_id":"a","expected_goals":3.2,"over_odds":2.0,"under_odds":1.8,
      "kickoff_utc":"2026-10-15T14:00:00Z",
      "odds_updated_utc":"2026-10-15T11:58:00Z",
      "odds_source":"test_bookmaker","model_version":"test_v1",
      "out_of_sample_calibration_verified":True,"fixture_identity_verified":True}

class EvidenceTests(unittest.TestCase):
    def test_valid_candidate_still_not_production(self):
        result=assess([BASE],now_utc=NOW)
        self.assertEqual(result["candidate_count"],1)
        self.assertEqual(result["production_recommendations"],"DISABLED")
    def test_stale_quote(self):
        row={**BASE,"odds_updated_utc":"2026-10-15T11:40:00Z"}
        self.assertEqual(assess([row],now_utc=NOW)["candidate_count"],0)
    def test_unverified_calibration(self):
        row={**BASE,"out_of_sample_calibration_verified":False}
        self.assertEqual(assess([row],now_utc=NOW)["candidate_count"],0)
    def test_started_match(self):
        row={**BASE,"kickoff_utc":"2026-10-15T11:59:00Z"}
        self.assertEqual(assess([row],now_utc=NOW)["candidate_count"],0)
    def test_missing_source(self):
        row={**BASE,"odds_source":""}
        self.assertEqual(assess([row],now_utc=NOW)["candidate_count"],0)

if __name__=="__main__":
    unittest.main()
