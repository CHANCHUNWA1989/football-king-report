import copy
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from ops.research_unified_batch_replay_v38 import reconcile, MAX_EVENTS
from ops.research_unified_prematch_replay_v35 import freeze
from ops.research_unified_prematch_audit_v34 import Forecast
from ops.research_market_provenance_v1 import Quote

ROOT = Path(__file__).resolve().parents[2]

def fixture(event):
    now = datetime(2026,11,27,12,tzinfo=timezone.utc)
    kick = now + timedelta(hours=3)
    fs = [Forecast(event,kick,now,"m"+str(i),"f"+str(i),1.5+i*.1,1.1)
          for i in range(2)]
    qs = [Quote("p"+str(i),"book",event,m,s,l,1.9,now,kick,
                upstream_provider="u"+str(i))
          for m,s,l in [("handicap","home",-.25),("handicap","away",-.25),
                        ("totals","over",2.75),("totals","under",2.75)]
          for i in range(2)]
    return freeze(event_id=event,kickoff=kick,now=now,forecasts=fs,
                  quotes=qs,handicap_line=-.25,totals_line=2.75,root=ROOT)

class BatchV38(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a, cls.b = fixture("a"), fixture("b")

    def check(self, expected, records, success=False):
        r = reconcile(expected,records,root=ROOT)
        self.assertIs(r["batch_replay_verified"],success)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        for k in ("roster_authenticated","source_identity_authenticated",
                  "external_timestamp_verified","training_admission",
                  "qualified_for_production","verified_executable_ev"):
            self.assertIs(r[k],False)
        return r

    def test_complete_order_invariant(self):
        a=self.check(["a","b"],[self.a,self.b],True)
        self.assertEqual(a,self.check(["b","a"],[self.b,self.a],True))
        self.assertEqual(a["verified_event_count"],2)

    def test_missing(self):
        self.assertEqual(self.check(["a","b"],[self.a])["missing_ids"],["b"])

    def test_unexpected(self):
        self.assertEqual(self.check(["a"],[self.a,self.b])["unexpected_ids"],["b"])

    def test_duplicate(self):
        r=self.check(["a"],[self.a,self.a])
        self.assertEqual(r["duplicate_ids"],["a"])
        self.assertEqual(r["verified_event_count"],0)

    def test_tampered_replay(self):
        bad=copy.deepcopy(self.a)
        bad["quotes"][0]["decimal_odds"]=3
        self.assertEqual(self.check(["a"],[bad])["failed_ids"],["a"])

    def test_malformed(self):
        self.assertEqual(self.check(["a"],[self.a,None])["malformed_record_count"],1)

    def test_invalid_rosters(self):
        for roster in ([],["a","a"],[" a"],[None],"a",list(map(str,range(MAX_EVENTS+1)))):
            with self.subTest(roster=roster):
                self.assertEqual(self.check(roster,[])["reason"],"INVALID_EXPECTED_ROSTER")

    def test_invalid_batch(self):
        for batch in (None,"a",[None]*(MAX_EVENTS+1)):
            self.assertEqual(self.check(["a"],batch)["reason"],"INVALID_RECORD_BATCH")

    def test_verifier_exception(self):
        with patch("ops.research_unified_batch_replay_v38.verify",side_effect=RecursionError):
            self.assertEqual(self.check(["a"],[self.a])["failed_ids"],["a"])

    def test_forged_permission(self):
        with patch("ops.research_unified_batch_replay_v38.verify",return_value={
            "replay_verified":True,"status":"HOLD","production_recommendations":"DISABLED",
            "external_timestamp_verified":False,"source_identity_authenticated":False,
            "training_admission":True,"qualified_for_production":False}):
            self.assertEqual(self.check(["a"],[self.a])["failed_ids"],["a"])

if __name__=="__main__":
    unittest.main()
