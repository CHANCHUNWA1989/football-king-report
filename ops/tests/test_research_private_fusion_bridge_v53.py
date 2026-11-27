import json
import unittest
from copy import deepcopy
from ops.research_private_fusion_bridge_v53 import prepare,recheck
from ops.tests.test_research_private_propline_v43 import fixture,NOW
from ops.tests.test_research_prospective_fusion_v38 import example

def args():
    d=fixture()
    return dict(primary_raw=None,private_batches=[{"raw":json.dumps({"events":[d]}).encode(),
        "league":"epl","captured_utc":NOW.isoformat()}],
        history_raw=json.dumps({"history":example()["history"]}).encode(),
        target=dict(league="epl",home=d["home_team"],away=d["away_team"],kickoff_utc=d["commence_time"]),
        as_of=NOW.isoformat())

class PrivateBridgeTests(unittest.TestCase):
    def test_private_receipt_and_full_recheck(self):
        a=args();p,r=prepare(**a)
        self.assertEqual(r["local_receipts"],1)
        self.assertTrue(p["private_only"])
        self.assertFalse(p["public_signing_allowed"])
        self.assertFalse(r["source_authenticity_verified"])
        self.assertNotIn("Arsenal",json.dumps(r))
        self.assertNotIn("receipt",r)
        self.assertEqual(recheck(p,**a)[0],p)
    def test_tamper_rejected(self):
        a=args();p,_=prepare(**a)
        bad=deepcopy(p);bad["receipt"]["candidate"]["weight"]=.99
        with self.assertRaises(ValueError):recheck(bad,**a)
    def test_wrong_target_abstains(self):
        a=args();a["target"]["away"]="Liverpool"
        p,r=prepare(**a)
        self.assertIsNone(p);self.assertEqual(r["local_receipts"],0)
    def test_duplicate_market_abstains(self):
        a=args();b=a["private_batches"][0];d=fixture();e=deepcopy(d);e["id"]="other"
        b["raw"]=json.dumps({"events":[d,e]}).encode()
        self.assertIsNone(prepare(**a)[0])
    def test_history_future_rejected(self):
        a=args();d=example()["history"];d[0]["observed_utc"]=NOW.isoformat()
        a["history_raw"]=json.dumps({"history":d}).encode()
        with self.assertRaises(ValueError):prepare(**a)
    def test_no_target_outcome(self):
        a=args();a["target"]["y"]=0
        with self.assertRaises(ValueError):prepare(**a)
