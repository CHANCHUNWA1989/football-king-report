import copy
import hashlib
import json
import unittest
from unittest.mock import patch
from ops.research_snapshot_replay_v3 import capture,replay,source_manifest,MAX_BYTES

def request():
    a={"publisher":"A","upstream":"feed-A","bookmaker":"book","fixture_id":"synthetic",
       "kickoff":"2026-11-27T20:15:00+08:00","observed_at":"2026-11-27T20:11:00+08:00",
       "odds":{"home":2.28,"draw":3.5,"away":2.45},"asian":[]}
    b=copy.deepcopy(a)
    b.update(publisher="B",upstream="feed-B")
    return {"fixture_id":"synthetic","kickoff":a["kickoff"],"as_of":"2026-11-27T20:12:00+08:00",
            "rates":[1.56,1.77],"rates_at":"2026-11-27T20:00:00+08:00","snapshots":[a,b]}

def raw_request():
    return json.dumps(request()).encode()

class ReplayTests(unittest.TestCase):
    def check_hold(self,r):
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertEqual(r["authenticated_samples"],0)
        for key in ("certified_ev","independent_oos_proven","source_authenticity_verified","model_promotion_allowed"):
            self.assertIs(r[key],False)
    def test_valid_roundtrip(self):
        raw=raw_request()
        receipt=capture(raw)
        self.check_hold(receipt)
        self.assertEqual(receipt["raw_sha256"],hashlib.sha256(raw).hexdigest())
        self.assertEqual(len(receipt["source_manifest"]["files"]),5)
        r=replay(raw,json.loads(json.dumps(receipt)))
        self.check_hold(r)
        self.assertTrue(r["replay_passed"])
        self.assertFalse(r["independent_attestation"])
    def test_byte_change(self):
        raw=raw_request()
        receipt=capture(raw)
        for altered in (raw+b" ",json.dumps(request(),sort_keys=True).encode()):
            r=replay(altered,receipt)
            self.check_hold(r)
            self.assertFalse(r["replay_passed"])
    def test_tampered_receipt_with_recomputed_digest(self):
        raw=raw_request()
        receipt=capture(raw)
        receipt["result"]["scenario"]["one_x_two"]["home"]["scenario_probability"]=0.99
        receipt.pop("receipt_sha256")
        receipt["receipt_sha256"]=hashlib.sha256(json.dumps(receipt,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
        self.assertFalse(replay(raw,receipt)["replay_passed"])
    def test_source_drift(self):
        raw=raw_request()
        receipt=capture(raw)
        changed=copy.deepcopy(source_manifest())
        changed["files"]["research_multimodel_v1.py"]="0"*64
        with patch("ops.research_snapshot_replay_v3.source_manifest",return_value=changed):
            self.assertFalse(replay(raw,receipt)["replay_passed"])
        with patch("ops.research_snapshot_replay_v3.source_manifest",side_effect=[receipt["source_manifest"],changed]):
            with self.assertRaises(ValueError):capture(raw)
    def test_reject_invalid_bytes(self):
        raw=raw_request()
        for altered in (b"",b"x"*(MAX_BYTES+1),b"\xff",raw.replace(b'"fixture_id": "synthetic"',b'"fixture_id": "synthetic", "fixture_id": "synthetic"',1),
                        raw.replace(b"1.56",b"NaN",1),raw.replace(b"1.56",b"1e999",1),b"[]"):
            with self.subTest(raw=altered[:100]):
                self.assertFalse(replay(altered,{})["replay_passed"])
    def test_reject_source_conflict(self):
        doc=request()
        doc["snapshots"][1]["odds"]["home"]=2.3
        with self.assertRaises(ValueError):capture(json.dumps(doc).encode())
    def test_no_promotion_by_receipt(self):
        raw=raw_request()
        receipt=capture(raw)
        receipt["status"]="READY"
        r=replay(raw,receipt)
        self.check_hold(r)
        self.assertFalse(r["replay_passed"])
if __name__=="__main__":
    unittest.main()
