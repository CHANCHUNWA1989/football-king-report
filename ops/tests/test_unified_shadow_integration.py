import copy
import math
import unittest
from datetime import datetime, timezone
from ops.unified_shadow_integration import distribution, evaluate


class UnifiedShadowIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,28,0,0,tzinfo=timezone.utc)
        h=a=1.2
        weights=[math.exp(-h)*h**i/math.factorial(i) for i in range(12)]
        draw=sum(x*x for x in weights)/sum(weights)**2
        self.row={"league":"epl","event_id":"test:1","kickoff_utc":"2026-11-28T03:00:00+00:00",
                  "prediction_utc":"2026-11-27T23:55:00+00:00",
                  "training_cutoff_local_day":"2026-11-27",
                  "training_observations_sha256":"a"*64,"training_games":100,
                  "model":"poisson-shrinkage-unvalidated-v4.1",
                  "calibrated":False,"production_recommendations":"DISABLED",
                  "expected_home_goals":h,"expected_away_goals":a,
                  "p_home":(1-draw)/2,"p_draw":draw,"p_away":(1-draw)/2}
        self.batch={"schema":"football-king-uncalibrated-shadow-1","status":"SHADOW_ONLY",
                    "production_recommendations":"DISABLED","model_calibrated":False,
                    "as_of_utc":"2026-11-27T23:56:00+00:00","predictions_count":1,
                    "predictions":[self.row]}
    def run_batch(self):
        result=evaluate(self.batch,{},self.now)
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(result["production_recommendations"],"DISABLED")
        self.assertFalse(result["positive_ev_verified"])
        self.assertEqual(result["recommendation_count"],0)
        return result
    def test_valid_batch_and_distribution(self):
        out=self.run_batch()
        self.assertEqual(len(out["rows"]),1)
        p=out["rows"][0]["probabilities"]
        self.assertAlmostEqual(p["p_home"]+p["p_draw"]+p["p_away"],1)
        self.assertAlmostEqual(p["p_home"],p["p_away"])
        self.assertAlmostEqual(p["p_over_2_5"],1-math.exp(-2.4)*(1+2.4+2.4**2/2))
        self.assertAlmostEqual(p["p_btts"],(1-math.exp(-1.2))**2)
    def test_stale(self):
        self.batch["as_of_utc"]="2026-11-27T22:00:00+00:00"
        self.assertFalse(self.run_batch()["rows"])
    def test_future(self):
        self.batch["as_of_utc"]="2026-11-28T00:01:00+00:00"
        self.assertFalse(self.run_batch()["rows"])
    def test_kickoff(self):
        self.row["kickoff_utc"]="2026-11-28T00:05:00+00:00"
        self.assertFalse(self.run_batch()["rows"])
    def test_duplicate(self):
        self.batch["predictions"].append(copy.deepcopy(self.row))
        self.batch["predictions_count"]=2
        self.assertFalse(self.run_batch()["rows"])
    def test_leakage(self):
        self.row["training_cutoff_local_day"]="2026-11-28"
        self.assertFalse(self.run_batch()["rows"])
    def test_legacy_mismatch(self):
        self.row["p_home"]=0.9
        self.assertFalse(self.run_batch()["rows"])
    def test_invalid_rate(self):
        for value in (True,float("nan"),float("inf"),0,6):
            with self.subTest(value=value),self.assertRaises(ValueError):
                distribution(value,1)
    def test_count_mismatch(self):
        self.batch["predictions_count"]=2
        self.assertFalse(self.run_batch()["rows"])
    def test_unsafe_state(self):
        self.batch["production_recommendations"]="ENABLED"
        self.assertFalse(self.run_batch()["rows"])
    def test_collection_guard_not_overridden(self):
        r=evaluate(self.batch,{"schema":"football-king-free-market-collection-status-v1",
                 "collection_status":"HOLD","collection_reason":"FREE_QUOTA_GUARD"},self.now)
        self.assertEqual(r["market_collection_reason"],"FREE_QUOTA_GUARD")
        self.assertFalse(r["executable_market_quotes"])
        self.assertEqual(r["recommendation_count"],0)

if __name__=="__main__":
    unittest.main()
