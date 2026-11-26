import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_core_real_observations import research, epoch_iso


class LiveCoreTests(unittest.TestCase):
    def setUp(self):
        self.now = 1795680240
        fid = "test-real-shaped-fixture"
        state = dict(fixture_id=fid,origin="publisher-a",observed=self.now-5,
                     received=self.now-3,minute=45,home=0,away=0,
                     red_home=1,red_away=0,phase="SECOND_HALF")
        self.a = dict(state=state,url="https://a.example/match",payload_sha256="a"*64)
        self.b = dict(state={**state,"origin":"publisher-b"},url="https://b.example/match",
                      payload_sha256="b"*64)
        self.kw = dict(now=self.now,kickoff_utc=epoch_iso(self.now-3600),
                       prematch=dict(fixture_id=fid,model_id="test-prior",
                           forecast_utc=epoch_iso(self.now-4500),
                           inputs_available_utc=epoch_iso(self.now-4600),
                           expected_home_goals=1.3,expected_away_goals=1.1,
                           input_sha256="c"*64,production_recommendations="DISABLED",
                           calibrated=False),
                       markets=[dict(market="totals",side="UNDER",line=1.25),
                                dict(market="asian_handicap",side="AWAY",line=0.25),
                                dict(market="h2h",side="AWAY",line=None)],
                       xg=dict(fixture_id=fid,observed=self.now-5,minute=45,
                               home=.28,away=.39,source_url="https://c.example/match"))

    def run_case(self):
        r = research(self.a,self.b,**self.kw)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        for key in ("source_authenticated","source_independence_verified","model_calibrated",
                    "model_scoring_eligible","positive_ev_verified","betting_recommendation_allowed"):
            self.assertIs(r[key],False)
        return r

    def rejected(self):
        self.assertNotIn("probabilities_1x2",self.run_case())

    def test_real_shaped_research(self):
        r = self.run_case()
        self.assertEqual(r["research_status"],"RESEARCH_ONLY")
        self.assertAlmostEqual(sum(r["probabilities_1x2"].values()),1)
        self.assertEqual(r["xg_claim_same_cut"],self.kw["xg"])
        self.assertFalse(r["xg_used_by_model"])
        self.assertIsNone(r["model_edge"])
        self.assertEqual(r["verified_forward_sample_credit"],0)
        for m in r["market_distributions"]:
            self.assertAlmostEqual(sum(m["outcome_probabilities"].values()),1)

    def test_missing_xg_not_zero(self):
        self.kw["xg"]=None
        self.assertIsNone(self.run_case()["xg_claim_same_cut"])

    def test_stale(self):
        self.a["state"]["observed"]=self.now-91
        self.rejected()

    def test_future(self):
        self.b["state"]["received"]=self.now+1
        self.rejected()

    def test_conflicting_card(self):
        self.b["state"]["red_home"]=0
        self.rejected()

    def test_duplicate_payload(self):
        self.b["payload_sha256"]=self.a["payload_sha256"]
        self.rejected()

    def test_duplicate_host(self):
        self.b["url"]="https://www.a.example/other"
        self.rejected()

    def test_wrong_xg_minute(self):
        self.kw["xg"]["minute"]=38
        self.rejected()

    def test_bad_market(self):
        self.kw["markets"][0]["line"]=1.3
        self.rejected()

    def test_lookahead(self):
        self.kw["prematch"]["forecast_utc"]=epoch_iso(self.now)
        self.rejected()

    def test_synthetic(self):
        self.a["state"]["fixture_id"]="synthetic-1"
        self.rejected()

    def test_rollback(self):
        self.kw["previous"]={**self.a["state"],"minute":46}
        self.rejected()

    def test_no_prior(self):
        self.kw["prematch"]=None
        self.rejected()

    def test_red_effect_direction(self):
        r=self.run_case()["probabilities_1x2"]["AWAY"]
        for s in (self.a,self.b):
            s["state"]["red_home"]=0
        self.assertLess(self.run_case()["probabilities_1x2"]["AWAY"],r)


if __name__=="__main__":
    unittest.main()
