import unittest
from shadow_research_readiness import summarize

def inputs():
    coverage={"status":"HOLD","production_recommendations":"DISABLED","matured_unmatched_count":1,
              "matured_unmatched_fixtures":[{"fixture_id":"fixture-1","home":"Home","away":"Away","kickoff_utc":"2026-10-10T12:00:00+00:00"}],
              "source_agreements":33,"eligible_bundesliga_pairs":27,"source_stale_14d":True}
    probe={"status":"HOLD","production_recommendations":"DISABLED","independently_verified":False,
           "eligible_for_model_scoring":False,"both_sources_name_overlap_fixture_ids":["fixture-1"]}
    corr={"production_recommendations":"DISABLED"}
    daily={"production_recommendations":"DISABLED","valid_fixtures":0}
    return coverage,probe,corr,daily

class ReadinessTests(unittest.TestCase):
    def test_research_only_and_blockers(self):
        result=summarize(*inputs())
        self.assertEqual(result["valid_scored_fixtures"],0)
        self.assertEqual(result["remaining"],1000)
        self.assertEqual(result["matured_awaiting_ft"],1)
        self.assertFalse(result["research_queue"][0]["model_scoring_eligible"])
        self.assertEqual(result["status"],"HOLD")
    def test_rejects_production_flag(self):
        data=list(inputs())
        data[3]["production_recommendations"]="ENABLED"
        with self.assertRaises(ValueError):
            summarize(*data)
    def test_rejects_fake_verified_probe(self):
        data=list(inputs())
        data[1]["independently_verified"]=True
        with self.assertRaises(ValueError):
            summarize(*data)
    def test_rejects_invalid_queue(self):
        data=list(inputs())
        data[0]["matured_unmatched_count"]=2
        with self.assertRaises(ValueError):
            summarize(*data)

if __name__=="__main__":
    unittest.main()
