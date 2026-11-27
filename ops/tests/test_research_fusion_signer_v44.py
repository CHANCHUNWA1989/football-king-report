import json
import unittest
from datetime import datetime,timezone,timedelta
from ops.tests.test_research_prospective_fusion_v38 import example,raw,NOW
from ops.research_fusion_signer_v44 import prepare
from ops.research_prospective_fusion_v38 import replay

CLOCK=datetime.fromisoformat(NOW.replace("Z","+00:00"))
def dispatch():
    d=example()
    d.pop("forecast_utc")
    d["schema"]="prospective-fusion-dispatch-v44"
    return d

class FusionSignerTests(unittest.TestCase):
    def test_runner_clock_and_exact_replay(self):
        b,r=prepare(raw(dispatch()),runner_clock=CLOCK)
        doc=json.loads(b);receipt=json.loads(r)
        self.assertEqual(doc["forecast_utc"],CLOCK.isoformat())
        self.assertEqual(replay(receipt,b),receipt)
        self.assertFalse(receipt["source_authenticity_verified"])
        self.assertFalse(receipt["external_time_witness_verified"])
        self.assertEqual(receipt["production_recommendations"],"DISABLED")
    def test_reject_caller_clock_and_target_outcome(self):
        for field,value in (("forecast_utc",NOW),("y",0)):
            d=dispatch();d[field]=value
            with self.assertRaises(ValueError):prepare(raw(d),runner_clock=CLOCK)
    def test_reject_stale_or_future_market(self):
        for t in ("2026-11-28T10:59:59Z","2026-11-28T12:00:01Z"):
            d=dispatch();d["market"]["captured_utc"]=t
            with self.assertRaises(ValueError):prepare(raw(d),runner_clock=CLOCK)
    def test_reject_naive_or_late_clock(self):
        for clock in (CLOCK.replace(tzinfo=None),CLOCK+timedelta(hours=3)):
            with self.assertRaises(ValueError):prepare(raw(dispatch()),runner_clock=clock)
    def test_reject_oversize_or_bad_schema(self):
        with self.assertRaises(ValueError):prepare(b"x"*60001,runner_clock=CLOCK)
        d=dispatch();d["schema"]="unknown"
        with self.assertRaises(ValueError):prepare(raw(d),runner_clock=CLOCK)
