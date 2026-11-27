import copy
import unittest
from ops.research_unified_snapshot_consensus_v2 import compare_snapshots

class SnapshotConsensusTests(unittest.TestCase):
    def setUp(self):
        a=dict(publisher="Publisher A",upstream="Feed A",bookmaker="Book",
               fixture_id="synthetic",kickoff="2026-11-27T20:15:00+08:00",
               observed_at="2026-11-27T20:11:00+08:00",
               odds={"home":2.28,"draw":3.5,"away":2.45},
               asian=[dict(market="handicap",selection=s,line=-0.25,decimal_odds=1.9)
                      for s in ("home","away")])
        b=copy.deepcopy(a)
        b.update(publisher="Publisher B",upstream="Feed B",observed_at="2026-11-27T12:11:30Z")
        self.args=dict(fixture_id="synthetic",kickoff=a["kickoff"],as_of="2026-11-27T20:12:00+08:00",
                       rates=(1.56,1.77),rates_at="2026-11-27T20:00:00+08:00",snapshots=[a,b])
    def check_safety(self,r):
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        for key in ("certified_ev","source_authenticity_verified","upstream_independence_verified",
                    "independent_oos_proven","model_promotion_allowed"):
            self.assertIs(r[key],False)
    def test_success_and_order_invariance(self):
        a=compare_snapshots(**self.args)
        self.check_safety(a)
        self.assertTrue(a["structural_consensus_passed"])
        self.assertEqual(a["complete_asian_pairs"],1)
        self.assertEqual(a["scenario"]["quote_age_seconds"],60)
        b=copy.deepcopy(self.args)
        b["snapshots"].reverse()
        b["snapshots"][0]["asian"].reverse()
        self.assertEqual(a,compare_snapshots(**b))
    def test_mismatch(self):
        changes=[dict(publisher=" publisher a "),dict(upstream=" feed a "),dict(bookmaker="Different"),
                 dict(fixture_id="different"),dict(kickoff="2026-11-27T20:16:00+08:00"),
                 dict(observed_at="2026-11-27T20:09:59+08:00"),
                 dict(observed_at="2026-11-27T20:12:01+08:00"),
                 dict(observed_at="2026-11-27T20:06:59+08:00"),
                 dict(odds={"home":2.3,"draw":3.5,"away":2.45}),
                 dict(asian=[])]
        for change in changes:
            with self.subTest(change=change):
                args=copy.deepcopy(self.args)
                args["snapshots"][1].update(change)
                r=compare_snapshots(**args)
                self.check_safety(r)
                self.assertFalse(r["structural_consensus_passed"])
                self.assertNotIn("scenario",r)
    def test_bad_pair_and_duplicate(self):
        for mode in ("missing","duplicate","negative_totals"):
            args=copy.deepcopy(self.args)
            for s in args["snapshots"]:
                if mode=="missing":s["asian"].pop()
                elif mode=="duplicate":s["asian"].append(s["asian"][0])
                else:s["asian"]=[dict(market="totals",selection=x,line=-0.25,decimal_odds=1.9) for x in ("over","under")]
            r=compare_snapshots(**args)
            self.check_safety(r)
            self.assertFalse(r["structural_consensus_passed"])
    def test_only_1x2_allowed_but_not_certified(self):
        for s in self.args["snapshots"]:s["asian"]=[]
        r=compare_snapshots(**self.args)
        self.check_safety(r)
        self.assertTrue(r["structural_consensus_passed"])
        self.assertEqual(r["complete_asian_pairs"],0)
    def test_evidence_digest_changes(self):
        r=compare_snapshots(**self.args)
        args=copy.deepcopy(self.args)
        args["rates"]=(1.57,1.77)
        self.assertNotEqual(r["snapshot_sha256"],compare_snapshots(**args)["snapshot_sha256"])
    def test_no_single_source_or_post_kickoff(self):
        for args in ({**self.args,"snapshots":self.args["snapshots"][:1]},
                     {**self.args,"as_of":self.args["kickoff"]}):
            r=compare_snapshots(**args)
            self.check_safety(r)
            self.assertFalse(r["structural_consensus_passed"])

if __name__=="__main__":
    unittest.main()
