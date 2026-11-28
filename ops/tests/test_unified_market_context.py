import copy
import unittest
from datetime import datetime, timezone
from ops.unified_market_context import readiness


class UnifiedMarketContextTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,28,0,0,tzinfo=timezone.utc)
        self.pred="2026-11-27T23:58:00+00:00"
        self.kick="2026-11-28T03:00:00+00:00"
        self.snap="2026-11-27T23:55:00+00:00"
        self.updated="2026-11-27T23:54:00+00:00"
        self.model={"league":"epl","event_id":"test:1","kickoff_utc":self.kick,
                    "prediction_utc":self.pred,"calibrated":False,
                    "production_recommendations":"DISABLED",
                    "probabilities":{"p_home":.40,"p_draw":.30,"p_away":.30},
                    "legacy_probabilities":[.40,.30,.30]}
        self.unified={"schema":"football-king-unified-shadow-integration-v1","status":"HOLD",
                      "production_recommendations":"DISABLED","model_calibrated":False,
                      "positive_ev_verified":False,"recommendation_count":0,
                      "as_of_utc":self.pred,"rows":[self.model]}
        self.row={"league":"epl","forecast_event_id":"test:1","market_event_id":"market:1",
                  "kickoff_utc":self.kick,"prediction_utc":self.pred,
                  "market_snapshot_utc":self.snap,"market_updated_utc":self.updated,
                  "available_for_betting":False,"result":None,"historical_outcome":None,
                  "model":[.40,.30,.30],"market":[.35,.30,.35],
                  "production_recommendations":"DISABLED"}
        self.pairs={"status":"RESEARCH_ONLY","production_recommendations":"DISABLED",
                    "matched_count":1,"comparisons":[self.row]}
        self.obs={"league":"epl","source_event_id":"market:1","kickoff_utc":self.kick,
                  "market_last_update_utc":self.updated,"p_home":.35,"p_draw":.30,"p_away":.35,
                  "probabilities_are_no_vig_consensus":True,"prediction_or_value_bet":False}
        self.market={"schema":"football-king-market-consensus-v1","status":"RESEARCH_ONLY",
                     "provider":"the-odds-api.com/v4","market":"h2h",
                     "raw_bookmaker_quotes_redistributed":False,
                     "production_recommendations":"DISABLED","as_of_utc":self.snap,
                     "events":[self.obs]}
    def run_case(self):
        out=readiness(self.unified,self.pairs,self.market,None,None,None,self.now)
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(out["production_recommendations"],"DISABLED")
        self.assertFalse(out["executable_market_quotes"])
        self.assertFalse(out["positive_ev_verified"])
        self.assertEqual(out["recommendation_count"],0)
        return out
    def test_valid_research_pair(self):
        out=self.run_case()
        self.assertEqual(len(out["pairs"]),1)
        self.assertAlmostEqual(out["pairs"][0]["model_minus_consensus_probability"][0],.05)
        self.assertTrue(out["pairs"][0]["probability_difference_is_not_ev"])
    def test_stale_primary(self):
        self.market["as_of_utc"]="2026-11-27T20:00:00+00:00"
        self.assertFalse(self.run_case()["pairs"])
    def test_future_market(self):
        self.market["as_of_utc"]="2026-11-28T00:01:00+00:00"
        self.assertFalse(self.run_case()["pairs"])
    def test_wrong_event(self):
        self.row["forecast_event_id"]="test:2"
        self.assertFalse(self.run_case()["pairs"])
    def test_wrong_kickoff(self):
        self.obs["kickoff_utc"]="2026-11-28T03:01:00+00:00"
        self.assertFalse(self.run_case()["pairs"])
    def test_duplicate_pair(self):
        self.pairs["comparisons"].append(copy.deepcopy(self.row))
        self.pairs["matched_count"]=2
        self.assertFalse(self.run_case()["pairs"])
    def test_duplicate_observation(self):
        self.market["events"].append(copy.deepcopy(self.obs))
        self.assertFalse(self.run_case()["pairs"])
    def test_forged_vector(self):
        self.row["market"]=[.9,.05,.05]
        self.assertFalse(self.run_case()["pairs"])
    def test_model_vector_mismatch(self):
        self.row["model"]=[.8,.1,.1]
        self.assertFalse(self.run_case()["pairs"])
    def test_unsafe_pair(self):
        self.row["available_for_betting"]=True
        self.assertFalse(self.run_case()["pairs"])
    def test_late_quote(self):
        self.obs["market_last_update_utc"]=self.row["market_updated_utc"]="2026-11-27T23:59:00+00:00"
        self.assertFalse(self.run_case()["pairs"])
    def test_missing_batch(self):
        self.unified=None
        self.assertFalse(self.run_case()["pairs"])
    def test_source_status_not_a_quote(self):
        out=readiness(None,None,None,{"schema":"football-king-free-market-collection-status-v1",
            "production_recommendations":"DISABLED","collection_status":"HOLD",
            "collection_reason":"FREE_QUOTA_GUARD"},None,
            {"schema":"football-king-hkjc-tipsme-free-research-v1",
             "production_recommendations":"DISABLED","status":"NOT_CONFIGURED",
             "captured_utc":self.snap},self.now)
        self.assertTrue(out["sources"]["primary"]["last_reported_quota_hold"])
        self.assertTrue(out["sources"]["tipsme"]["last_reported_not_configured"])
        self.assertFalse(out["executable_market_quotes"])
        self.assertEqual(out["new_api_calls"],0)
        self.assertFalse(out["pairs"])


if __name__=="__main__":
    unittest.main()
