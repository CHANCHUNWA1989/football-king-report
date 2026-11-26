"""Deterministic synthetic stress and output quarantine, no network."""
import copy
import itertools
import math
import sys
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_inplay_state_challenger_vnext import sample
from test_v9_offline_intake_model_bridge import inputs
from test_vnext_offline_intake_e2e import Store
from test_live_snapshot_commitment import envelope,NOW
from live_snapshot_commitment import commitment
from inplay_state_challenger_vnext import predict,remaining_matrix
from score_distribution_vnext import market_distribution
from vnext_integrated_replay import replay
from v9_offline_intake_model_bridge import simulate,valid_pmf


class StressTests(unittest.TestCase):
    def test_108_score_rate_clock_card_scenarios(self):
        reverse = {"FULL_WIN":"FULL_LOSS","HALF_WIN":"HALF_LOSS","PUSH":"PUSH",
                   "HALF_LOSS":"HALF_WIN","FULL_LOSS":"FULL_WIN"}
        ko=datetime(2026,11,3,20,0,tzinfo=timezone.utc)
        count=0
        for minute,score,reds,rates in itertools.product(
                (10,50,89),((0,0),(0,2),(10,0),(10,10)),
                ((0,0),(1,0),(0,3)),((.1,.1),(5.5,.1),(.1,5.5))):
            with self.subTest(minute=minute,score=score,reds=reds,rates=rates):
                decision=(ko+timedelta(minutes=minute+1+(15 if minute>=45 else 0))).isoformat()
                out=predict(sample(score=score,minute=minute,decision=decision,
                                   reds=reds,home_rate=rates[0],away_rate=rates[1]))
                self.assertEqual(out["status"],"RESEARCH_ONLY")
                self.assertEqual(out["production_recommendations"],"DISABLED")
                self.assertFalse(out["model_scoring_eligible"])
                self.assertTrue(valid_pmf(out["fulltime_probabilities"],("HOME","DRAW","AWAY")))
                grid=remaining_matrix(out["remaining_expected_home_goals"],
                                      out["remaining_expected_away_goals"],*score)
                self.assertAlmostEqual(math.fsum(v for row in grid for v in row),1.0,places=9)
                for i,row in enumerate(grid):
                    for j,v in enumerate(row):
                        if i<score[0] or j<score[1]:
                            self.assertEqual(v,0)
                for market,s1,s2,line1,line2 in (
                        ("totals","OVER","UNDER",2.25,2.25),
                        ("asian_handicap","HOME","AWAY",-1.25,1.25)):
                    a=market_distribution(grid,market=market,side=s1,line=line1)["outcome_probabilities"]
                    b=market_distribution(grid,market=market,side=s2,line=line2)["outcome_probabilities"]
                    self.assertTrue(valid_pmf(a,reverse))
                    self.assertTrue(valid_pmf(b,reverse))
                    for k,v in reverse.items():
                        self.assertAlmostEqual(a[k],b[v],places=9)
                count+=1
        self.assertEqual(count,108)

    def run_bridge(self,store=None):
        e=envelope()
        with patch("urllib.request.OpenerDirector.open",side_effect=AssertionError("network forbidden")) as net:
            out=simulate(store if store is not None else Store(),intake=inputs(),
                         canonical_fixture="synthetic-ucl-001",envelope=e,
                         expected_digest=commitment(e))
            net.assert_not_called()
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(out["production_recommendations"],"DISABLED")
        self.assertFalse(out["positive_ev_verified"])
        return out

    def test_real_replay_passes_output_gate(self):
        self.assertTrue(self.run_bridge()["synthetic_model_executed"])

    def test_malformed_or_promoted_outputs_quarantined(self):
        e=envelope()
        good=replay(e,commitment(e),NOW)
        variants=[]
        for key,value in (("HOME",float("nan")),("DRAW",-0.1),("AWAY",True),("HOME",2.0)):
            bad=copy.deepcopy(good);bad["probabilities_1x2"][key]=value;variants.append(bad)
        for key,value in (("production_recommendations","ENABLED"),("positive_ev_verified",True),
                          ("model_edge",0.5),("actual_xg",1.5),("fixture_id","other")):
            bad=copy.deepcopy(good);bad[key]=value;variants.append(bad)
        bad=copy.deepcopy(good);bad["diagnostic_distributions"][0]["line"]=3.5;variants.append(bad)
        bad=copy.deepcopy(good);bad["diagnostic_distributions"][0]["outcome_probabilities"]["FULL_WIN"]=float("inf");variants.append(bad)
        bad=copy.deepcopy(good);bad["diagnostic_distributions"][0]["actual_market_quote_verified"]=True;variants.append(bad)
        bad=copy.deepcopy(good);bad["diagnostic_distributions"].pop();variants.append(bad)
        for i,bad in enumerate(variants):
            with self.subTest(case=i),patch("v9_offline_intake_model_bridge.replay",return_value=bad):
                out=self.run_bridge()
                self.assertEqual(out["reason"],"MODEL_OUTPUT_QUARANTINED")
                self.assertFalse(out["synthetic_model_executed"])
                self.assertNotIn("synthetic_probabilities_1x2",out)

    def test_runtime_failure_isolated_and_reservation_not_refunded(self):
        store=Store()
        with patch("v9_offline_intake_model_bridge.replay",side_effect=RuntimeError("private diagnostic")):
            out=self.run_bridge(store)
        self.assertEqual(out["reason"],"MODEL_EXECUTION_QUARANTINED")
        self.assertNotIn("private diagnostic",str(out))
        self.assertTrue(out["simulated_reservation"])
        self.assertEqual(len(store.state.attempts),1)
        self.assertEqual(self.run_bridge(store)["reason"],"INTAKE_REJECTED")
