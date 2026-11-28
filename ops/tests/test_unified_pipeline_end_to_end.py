"""Exercise the actual producer -> unified scores -> existing market pair -> bridge.

All input fixtures are synthetic. No network, secrets, deployment, or evidence credit.
"""
import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from shadow_forecast import predict_league
from market_pair import pair
from unified_shadow_integration import evaluate
from unified_market_context import readiness


class UnifiedPipelineEndToEnd(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,28,0,0,tzinfo=timezone.utc)
        self.pred=self.now-timedelta(minutes=2)
        self.kick=self.now+timedelta(hours=3)
        history=[]
        for i in range(40):
            h,a=("Everton","Arsenal") if i%2==0 else ("Arsenal","Everton")
            history.append({"date":(self.pred-timedelta(days=i+2)).date().isoformat(),
                "home":h,"away":a,"score_ft":[i%3,(i+1)%3],"status":"FINISHED"})
        history.append({"date":"2026-11-28","home":"Everton","away":"Arsenal",
            "kickoff_utc":self.kick.isoformat(),"event_id":"fixture:synthetic",
            "status":"SCHEDULED"})
        rows=predict_league(history,"epl",self.pred)
        self.assertEqual(len(rows),1)
        self.shadow={"schema":"football-king-uncalibrated-shadow-1","status":"SHADOW_ONLY",
            "production_recommendations":"DISABLED","model_calibrated":False,
            "as_of_utc":self.pred.isoformat(),"predictions_count":len(rows),"predictions":rows}
        self.market={"schema":"football-king-market-consensus-v1","status":"RESEARCH_ONLY",
            "provider":"the-odds-api.com/v4","market":"h2h","production_recommendations":"DISABLED",
            "raw_bookmaker_quotes_redistributed":False,"as_of_utc":(self.pred-timedelta(minutes=1)).isoformat(),
            "events":[{"league":"epl","source_event_id":"market:synthetic",
                "home":"Everton","away":"Arsenal","kickoff_utc":self.kick.isoformat(),
                "market_last_update_utc":(self.pred-timedelta(minutes=2)).isoformat(),
                "p_home":.4,"p_draw":.3,"p_away":.3,"contributing_bookmakers":3,
                "probabilities_are_no_vig_consensus":True,"prediction_or_value_bet":False}]}

    def execute_pipeline(self):
        u=evaluate(self.shadow,{},self.now)
        p=pair(self.shadow,self.market)
        m=readiness(u,p,self.market,None,None,None,self.now)
        for item in (u,m):
            self.assertEqual(item["status"],"HOLD")
            self.assertEqual(item["production_recommendations"],"DISABLED")
            self.assertEqual(item["recommendation_count"],0)
            self.assertFalse(item["positive_ev_verified"])
            self.assertFalse(item["executable_market_quotes"])
        return u,p,m

    def test_real_producer_and_pairing_schema(self):
        original=copy.deepcopy(self.shadow)
        u,p,m=self.execute_pipeline()
        self.assertEqual(self.shadow,original)
        self.assertEqual(len(u["rows"]),1)
        self.assertEqual(len(u["rows"][0]["asian_scenarios"]),84)
        self.assertEqual(len(u["rows"][0]["dc_sensitivity"]["scenarios"]),4)
        self.assertEqual(p["matched_count"],1)
        self.assertEqual(len(m["pairs"]),1)
        self.assertEqual(m["pairs"][0]["event_id"],"fixture:synthetic")
        self.assertTrue(m["pairs"][0]["probability_difference_is_not_ev"])

    def test_stale_market_cannot_remove_model_or_create_pair(self):
        self.market["as_of_utc"]=(self.now-timedelta(hours=3)).isoformat()
        self.market["events"][0]["market_last_update_utc"]=self.market["as_of_utc"]
        u,p,m=self.execute_pipeline()
        self.assertEqual(len(u["rows"]),1)
        self.assertFalse(m["pairs"])

    def test_fixture_conflict_blocks_market_context(self):
        self.market["events"][0]["away"]="Arsenal Women"
        u,p,m=self.execute_pipeline()
        self.assertEqual(len(u["rows"]),1)
        self.assertEqual(p["matched_count"],0)
        self.assertFalse(m["pairs"])

    def test_kickoff_passed_blocks_unified_output(self):
        self.now=self.kick
        u,p,m=self.execute_pipeline()
        self.assertFalse(u["rows"])
        self.assertFalse(m["pairs"])

    def test_future_market_snapshot_blocks_context(self):
        self.market["as_of_utc"]=(self.pred+timedelta(seconds=1)).isoformat()
        self.market["events"][0]["market_last_update_utc"]=self.market["as_of_utc"]
        u,p,m=self.execute_pipeline()
        self.assertEqual(len(u["rows"]),1)
        self.assertEqual(p["matched_count"],0)
        self.assertFalse(m["pairs"])


if __name__=="__main__":
    unittest.main()
