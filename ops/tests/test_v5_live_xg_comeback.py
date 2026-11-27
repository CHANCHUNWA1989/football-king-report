import copy
import math
import unittest
from datetime import datetime,timezone
from ops.v5_live_xg_comeback import predict,distribution
from ops.red_card_forward_evidence import canonical

NOW=datetime(2026,11,25,21,5,5,tzinfo=timezone.utc)
S={"fixture_id":"fixture-test","publisher_id":"official","origin_group":"one","role":"OFFICIAL",
   "phase":"SECOND_HALF","clock_kind":"REGULATION_SECONDS_NO_STOPPAGE","clock_s":3600,
   "score":[0,1],"reds":[0,0],"kickoff_utc":"2026-11-25T19:45:00Z",
   "observed_utc":"2026-11-25T21:05:00Z","captured_utc":"2026-11-25T21:05:01Z"}
B={**S,"publisher_id":"other","origin_group":"two","role":"INDEPENDENT"}
P={"fixture_id":"fixture-test","model_id":"test-prior","training_cutoff_utc":"2026-11-24T00:00:00Z",
   "prediction_utc":"2026-11-25T18:00:00Z","rate_kind":"FULL_REGULATION_GOAL_EXPECTATION",
   "home_goals_expected":1.6,"away_goals_expected":1.2}
X=[{"fixture_id":"fixture-test","publisher_id":"xg","xg_model":"test-xg","clock_s":3000,
    "observed_utc":"2026-11-25T20:55:00Z","captured_utc":"2026-11-25T20:55:01Z","home_xg":.6,"away_xg":.5},
   {"fixture_id":"fixture-test","publisher_id":"xg","xg_model":"test-xg","clock_s":3600,
    "observed_utc":"2026-11-25T21:05:00Z","captured_utc":"2026-11-25T21:05:01Z","home_xg":.9,"away_xg":.7}]
CARD={"fixture_id":"fixture-test","player_id":"player-test","publisher_id":"official","origin_group":"one",
      "role":"OFFICIAL","event_type":"RED_CARD","side":"HOME","clock_s":3000,"prior_reds":[0,0],
      "score":[0,1],"kickoff_utc":"2026-11-25T19:45:00Z","event_utc":"2026-11-25T20:55:00Z",
      "captured_utc":"2026-11-25T20:55:01Z"}
class LiveTests(unittest.TestCase):
    def test_valid_scenario_and_mass(self):
        r=predict(S,B,P,X,now=NOW)
        self.assertEqual(r["reason"],"UNVERIFIED_SCENARIO_ONLY")
        self.assertEqual(r["status"],"HOLD")
        d=r["distribution"]
        for p in (d["1x2"],list(d["final_total_p"].values()),list(d["final_margin_p"].values())):
            self.assertAlmostEqual(sum(p),1)
        self.assertEqual(d["trailing_team_final_win_p"],d["1x2"][0])
        self.assertFalse(r["actual_xg_verified"])
    def test_card_effect_and_no_double_count(self):
        a={**S,"reds":[1,0]};b={**B,"reds":[1,0]}
        c={**CARD,"publisher_id":"other","origin_group":"two","role":"INDEPENDENT"}
        r=predict(a,b,P,X,official_card=canonical(CARD),independent_card=canonical(c),now=NOW)
        baseline=predict(S,B,P,X,now=NOW)
        self.assertLess(r["remaining_goal_rates"][0],baseline["remaining_goal_rates"][0])
        self.assertGreater(r["remaining_goal_rates"][1],baseline["remaining_goal_rates"][1])
        self.assertLess(r["distribution"]["1x2"][0],baseline["distribution"]["1x2"][0])
    def test_conflicts_and_stale(self):
        for b in ({**B,"score":[1,1]},{**B,"origin_group":"one"},{**B,"clock_s":3601},
                  {**B,"captured_utc":"2026-11-25T21:06:00Z"}):
            self.assertIsNone(predict(S,b,P,X,now=NOW)["distribution"])
        self.assertIsNone(predict(S,B,P,X,now=datetime(2026,11,25,21,7,tzinfo=timezone.utc))["distribution"])
    def test_future_or_missing_xg(self):
        for x in ([],[{**X[0],"home_xg":1.2},X[1]],[X[0],{**X[1],"captured_utc":"2026-11-25T21:06:00Z"}],
                  [X[0],{**X[1],"xg_model":"different"}]):
            self.assertIsNone(predict(S,B,P,x,now=NOW)["distribution"])
    def test_card_and_prior_rejected(self):
        self.assertIsNone(predict({**S,"reds":[1,0]},{**B,"reds":[1,0]},P,X,now=NOW)["distribution"])
        self.assertIsNone(predict(S,B,{**P,"prediction_utc":"2026-11-25T21:00:00Z"},X,now=NOW)["distribution"])
    def test_stress_648(self):
        n=0
        for h in range(3):
            for a in range(3):
                for rh in (.1,.3,.6,1.,2.,3.):
                    for ra in (.1,.3,.6,1.,2.,3.):
                        for factor in (.75,.9):
                            b=distribution(h,a,rh,ra);c=distribution(h,a,rh*factor,ra*1.25)
                            self.assertLessEqual(c["1x2"][0],b["1x2"][0]+1e-12)
                            self.assertAlmostEqual(sum(c["1x2"]),1)
                            self.assertAlmostEqual(sum(c["final_margin_p"].values()),1)
                            n+=1
        self.assertEqual(n,648)
