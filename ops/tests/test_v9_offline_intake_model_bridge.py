import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_vnext_offline_intake_e2e import Store
from test_live_snapshot_commitment import envelope,NOW
from live_snapshot_commitment import commitment
from vnext_direct_transport_offline import URL
from v9_offline_intake_model_bridge import simulate


def inputs():
    return dict(quota=dict(epoch="test",revision_floor=0,request_id="bridge1",consumer="runner",
                    now=NOW,observed=NOW,daily_remaining=100,minute_remaining=10),
                transport=dict(env={},response_url=URL,status=200,content_type="application/json",
                    body=json.dumps({"errors":[],"response":[{"fixture":{"id":11,
                    "status":{"short":"2H","elapsed":50}},"goals":{"home":0,"away":2}}]}).encode()),
                mapping=dict(primary_id=11,secondary_id=22),primary_observed=NOW-10,
                secondary=dict(fixture_id=22,publisher="synthetic_secondary",observed=NOW-8,
                    phase="2H",minute=50,home=0,away=2))


class BridgeTests(unittest.TestCase):
    def call(self, intake=None, e=None, digest=None, fixture="synthetic-ucl-001",store=None):
        e = envelope() if e is None else e
        with patch("urllib.request.OpenerDirector.open",side_effect=AssertionError("no network")) as net:
            out=simulate(store or Store(),intake=inputs() if intake is None else intake,
                         canonical_fixture=fixture,envelope=e,
                         expected_digest=commitment(e) if digest is None else digest)
            net.assert_not_called()
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(out["production_recommendations"],"DISABLED")
        self.assertEqual(out["real_requests"],0)
        for k in ("source_authenticated","source_independence_verified","actual_xg_verified",
                  "actual_live_odds_verified","positive_ev_verified","model_scoring_eligible","real_request_authorized"):
            self.assertIs(out[k],False)
        return out

    def test_real_parent_model_and_settlement(self):
        out=self.call()
        self.assertTrue(out["synthetic_model_executed"])
        self.assertAlmostEqual(sum(out["synthetic_probabilities_1x2"].values()),1.0)
        for m in out["synthetic_market_distributions"]:
            self.assertAlmostEqual(sum(m["outcome_probabilities"].values()),1.0)
        self.assertFalse(out["red_cards_verified"])
        self.assertIsNone(out["actual_xg"])
        self.assertIsNone(out["model_edge"])

    def test_intake_failure_prevents_model(self):
        a=inputs();a["secondary"]["home"]=1
        with patch("v9_offline_intake_model_bridge.replay") as m:
            out=self.call(intake=a)
            m.assert_not_called()
        self.assertEqual(out["reason"],"INTAKE_REJECTED")
        self.assertTrue(out["simulated_reservation"])

    def test_bound_state_mismatch_even_with_new_digest(self):
        for key,val in (("home",1),("minute",51),("observed",NOW-9),("fixture_id","synthetic-other")):
            e=envelope();e["a"][key]=val
            with patch("v9_offline_intake_model_bridge.replay") as m:
                out=self.call(e=e)
                m.assert_not_called()
            self.assertEqual(out["reason"],"INTAKE_MODEL_STATE_MISMATCH")

    def test_model_clock_mismatch(self):
        e=envelope();e["decision_epoch"]+=1
        self.assertEqual(self.call(e=e)["reason"],"INTAKE_MODEL_CLOCK_MISMATCH")

    def test_commitment_and_model_history(self):
        self.assertEqual(self.call(digest="0"*64)["reason"],"MODEL_REJECTED")
        e=envelope();e["previous_a"]=None
        self.assertEqual(self.call(e=e)["reason"],"MODEL_REJECTED")

    def test_replay_reservation(self):
        store=Store()
        self.assertTrue(self.call(store=store)["synthetic_model_executed"])
        with patch("v9_offline_intake_model_bridge.replay") as m:
            self.assertEqual(self.call(store=store)["reason"],"INTAKE_REJECTED")
            m.assert_not_called()

    def test_non_synthetic_fixture_refused(self):
        self.assertEqual(self.call(fixture="real-fixture")["reason"],"SYNTHETIC_FIXTURE_REQUIRED")

    def test_unsupported_phase(self):
        a=inputs()
        body=json.loads(a["transport"]["body"])
        body["response"][0]["fixture"]["status"]["short"]="HT"
        a["transport"]["body"]=json.dumps(body).encode()
        a["secondary"]["phase"]="HT"
        self.assertEqual(self.call(intake=a)["reason"],"UNSUPPORTED_MODEL_PHASE")
