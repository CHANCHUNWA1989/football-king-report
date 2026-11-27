import copy
import unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
from ops.research_unified_prematch_audit_v34 import Forecast
from ops.research_market_provenance_v1 import Quote
from ops.research_unified_prematch_replay_v35 import freeze,verify,digest

class ReplayV35(unittest.TestCase):
    def setUp(self):
        now=datetime(2026,11,27,12,tzinfo=timezone.utc)
        kick=now+timedelta(hours=3)
        fs=[Forecast("e",kick,now,"m"+str(i),"f"+str(i),1.5+i*.1,1.1) for i in range(2)]
        qs=[Quote("p"+str(i),"book","e",m,s,l,1.9,now,kick,upstream_provider="u"+str(i))
            for m,s,l in [("handicap","home",-.25),("handicap","away",-.25),
                          ("totals","over",2.75),("totals","under",2.75)] for i in range(2)]
        self.args=dict(event_id="e",kickoff=kick,now=now,forecasts=fs,quotes=qs,
                       handicap_line=-.25,totals_line=2.75,root=Path(__file__).resolve().parents[2])
        self.r=freeze(**self.args)
    def check(self,r):
        v=verify(r,root=self.args["root"])
        self.assertEqual(v["status"],"HOLD")
        self.assertFalse(v["training_admission"])
        self.assertFalse(v["source_identity_authenticated"])
        self.assertFalse(v["external_timestamp_verified"])
        self.assertFalse(v["qualified_for_production"])
        return v["replay_verified"]
    def rehash(self,r):
        r["sha256"]=digest({k:v for k,v in r.items() if k!="sha256"})
        return r
    def test_roundtrip(self):
        self.assertTrue(self.check(self.r))
    def test_order_invariant(self):
        args=dict(self.args,forecasts=self.args["forecasts"][::-1],quotes=self.args["quotes"][::-1])
        self.assertEqual(self.r,freeze(**args))
    def test_timezone_invariant(self):
        tz=timezone(timedelta(hours=8))
        args=dict(self.args,now=self.args["now"].astimezone(tz),kickoff=self.args["kickoff"].astimezone(tz))
        self.assertEqual(self.r,freeze(**args))
    def test_changed_price(self):
        r=copy.deepcopy(self.r)
        r["quotes"][0]["decimal_odds"]=3
        self.assertFalse(self.check(r))
        self.assertFalse(self.check(self.rehash(r)))
    def test_forged_diagnostic(self):
        r=copy.deepcopy(self.r)
        r["audit"]["diagnostics"]["handicap_home"]["min"]=1
        self.assertFalse(self.check(self.rehash(r)))
    def test_forged_training_permission(self):
        r=copy.deepcopy(self.r)
        r["training_admission"]=True
        self.assertFalse(self.check(self.rehash(r)))
    def test_source_drift(self):
        r=copy.deepcopy(self.r)
        r["source_manifest"]["ops/research_unified_prematch_audit_v34.py"]="0"*64
        self.assertFalse(self.check(self.rehash(r)))
    def test_stale(self):
        args=dict(self.args,now=self.args["now"]+timedelta(seconds=301))
        with self.assertRaises(ValueError):
            freeze(**args)
    def test_malformed(self):
        self.assertFalse(self.check({"forecasts":None}))

if __name__=="__main__":
    unittest.main()
