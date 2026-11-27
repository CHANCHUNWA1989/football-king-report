import json
import unittest
from copy import deepcopy
from ops.research_prospective_fusion_v38 import capture,replay

NOW="2026-11-28T12:00:00Z"
def example():
    return dict(schema="prospective-fusion-input-v38",event_id="new-1",league="epl",home="a",away="b",
        kickoff_utc="2026-11-28T15:00:00Z",forecast_utc=NOW,
        market=dict(captured_utc="2026-11-28T11:00:00Z",p=[.4,.3,.3],source_id="market",
                    evidence_sha256="a"*64),
        history=[dict(league="epl",home="a",away="c",kickoff_utc="2026-11-25T15:00:00Z",
                    observed_utc="2026-11-25T18:00:00Z",score=[2,1],source_id="source",
                    fixture_id="past-1",evidence_sha256="b"*64)])
def raw(d):return json.dumps(d).encode()
class ProspectiveFusionTests(unittest.TestCase):
    def test_roundtrip(self):
        b=raw(example());r=capture(b,as_of=NOW)
        self.assertEqual(replay(json.loads(json.dumps(r)),b),r)
        self.assertEqual(r["candidate"]["weight"],0)
        self.assertFalse(r["external_time_witness_verified"])
        self.assertFalse(r["training_admission"])
    def test_receipt_tamper_and_raw_tamper(self):
        b=raw(example());r=capture(b,as_of=NOW)
        bad=deepcopy(r);bad["candidate"]["weight"]=.1
        with self.assertRaises(ValueError):replay(bad,b)
        d=example();d["history"][0]["score"]=[3,1]
        with self.assertRaises(ValueError):replay(r,raw(d))
    def test_registration_and_lead(self):
        d=example();d["forecast_utc"]="2026-11-27T23:59:00Z"
        with self.assertRaises(ValueError):capture(raw(d),as_of=d["forecast_utc"])
        d=example();d["kickoff_utc"]="2026-11-28T12:09:59Z"
        with self.assertRaises(ValueError):capture(raw(d),as_of=NOW)
    def test_delay_boundary(self):
        d=example();d["history"][0]["observed_utc"]="2026-11-27T12:00:00Z"
        with self.assertRaises(ValueError):capture(raw(d),as_of=NOW)
    def test_no_outcome_field(self):
        d=example();d["y"]=0
        with self.assertRaises(ValueError):capture(raw(d),as_of=NOW)
    def test_duplicate_history(self):
        d=example();d["history"].append(deepcopy(d["history"][0]))
        with self.assertRaises(ValueError):capture(raw(d),as_of=NOW)
    def test_stale_market_receipt(self):
        d=example();d["market"]["captured_utc"]="2026-11-28T10:59:59Z"
        r=capture(raw(d),as_of=NOW)
        self.assertEqual(r["candidate"]["state"],"STALE_MARKET_ABSTAIN")
        self.assertIsNone(r["candidate"]["p"])
    def test_future_market(self):
        d=example();d["market"]["captured_utc"]="2026-11-28T12:00:01Z"
        with self.assertRaises(ValueError):capture(raw(d),as_of=NOW)
