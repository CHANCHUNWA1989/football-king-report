import copy
import json
import unittest
from ops.tests.test_research_live_intake_v4 import inputs
from ops.tests.test_research_unified_live_v2 import NOW
from ops.research_snapshot_replay_v3 import capture
from ops.research_prematch_live_bridge_v4 import link

def case():
    rows,policy=inputs()
    rows=[r for r in rows if r["kind"]!="quote"]
    prior=next(r for r in rows if r["kind"]=="prior")
    frozen=prior["captured_at"]
    kickoff=policy["fixtures"]["synthetic"]["kickoff"]
    p=dict(publisher="A",upstream="feedA",bookmaker="synthetic",fixture_id="synthetic",
           kickoff=kickoff,observed_at=frozen,odds={"home":2.3,"draw":3.4,"away":2.7},asian=[])
    q=dict(p,publisher="B",upstream="feedB")
    raw=json.dumps(dict(fixture_id="synthetic",kickoff=kickoff,as_of=frozen,
                        rates=[prior["payload"]["home_xg"],prior["payload"]["away_xg"]],
                        rates_at=prior["payload"]["updated"],snapshots=[p,q])).encode()
    return dict(prematch_raw=raw,prematch_receipt=capture(raw),
                live_raw_captures=[json.dumps(r).encode() for r in rows],
                policy=policy,as_of=NOW,model_release="synthetic")

class BridgeTests(unittest.TestCase):
    def check_hold(self,r):
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertEqual(r["authenticated_samples"],0)
        for key in ("source_authenticity_verified","independent_oos_proven","certified_ev","model_promotion_allowed","calibrated"):
            self.assertIs(r[key],False)
    def test_valid_link(self):
        r=link(**case())
        self.check_hold(r)
        self.assertTrue(r["structural_link_passed"])
        self.assertEqual(r["market_evidence"],"ABSENT")
        self.assertEqual(r["trailing_side"],"away")
        self.assertEqual(r["comeback_win_scenario"],r["dynamic"]["away"])
        self.assertAlmostEqual(sum(r["dynamic"][k] for k in ("home","draw","away")),1)
        self.assertNotIn("hypothetical_ev",r)
    def test_tampered_receipt_or_raw(self):
        for field in ("prematch_raw","prematch_receipt"):
            args=case()
            if field=="prematch_raw":args[field]+=b" "
            else:args[field]["status"]="READY"
            r=link(**args)
            self.check_hold(r)
            self.assertFalse(r["structural_link_passed"])
            self.assertNotIn("dynamic",r)
    def test_prior_mismatch(self):
        for field in ("home_xg","captured_at"):
            args=case()
            rows=[json.loads(raw) for raw in args["live_raw_captures"]]
            prior=next(r for r in rows if r["kind"]=="prior")
            if field=="home_xg":prior["payload"][field]+=0.1
            else:prior[field]="2026-11-27T08:01:00Z"
            args["live_raw_captures"]=[json.dumps(r).encode() for r in rows]
            r=link(**args)
            self.check_hold(r)
            self.assertFalse(r["structural_link_passed"])
    def test_red_card_response(self):
        args=case()
        base=link(**args)
        rows=[json.loads(raw) for raw in args["live_raw_captures"]]
        for row in rows:
            if row["kind"]=="score":row["payload"]["home_red"]=1
        args["live_raw_captures"]=[json.dumps(r).encode() for r in rows]
        r=link(**args)
        self.check_hold(r)
        self.assertTrue(r["structural_link_passed"])
        self.assertEqual(r["red_cards"],[1,0])
        self.assertLess(r["dynamic"]["home"],base["dynamic"]["home"])
        self.assertGreater(r["comeback_win_scenario"],base["comeback_win_scenario"])
    def test_red_card_disagreement_and_unexpected_quote(self):
        for mode in ("red","quote"):
            args=case()
            rows=[json.loads(raw) for raw in args["live_raw_captures"]]
            if mode=="red":next(r for r in rows if r["kind"]=="score")["payload"]["home_red"]=1
            else:rows.append(next(r for r in inputs()[0] if r["kind"]=="quote"))
            args["live_raw_captures"]=[json.dumps(r).encode() for r in rows]
            r=link(**args)
            self.check_hold(r)
            self.assertFalse(r["structural_link_passed"])
    def test_kickoff_and_provider_identity(self):
        for mode in ("kickoff","provider"):
            args=case()
            if mode=="kickoff":
                args["policy"]["fixtures"]["synthetic"]["kickoff"]="2026-11-27T08:39:00Z"
            else:args["policy"]["fixtures"]["synthetic"]["provider_ids"]["adapter0"]="other"
            self.assertFalse(link(**args)["structural_link_passed"])
    def test_tied_match_no_comeback(self):
        args=case()
        rows=[json.loads(raw) for raw in args["live_raw_captures"]]
        for row in rows:
            if row["kind"]=="score":row["payload"]["home"]=0
        args["live_raw_captures"]=[json.dumps(r).encode() for r in rows]
        r=link(**args)
        self.assertTrue(r["structural_link_passed"])
        self.assertIsNone(r["comeback_win_scenario"])
        self.assertIsNone(r["comeback_win_range"])
if __name__=="__main__":
    unittest.main()
