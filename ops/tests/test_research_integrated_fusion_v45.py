import json
import unittest
from pathlib import Path
from datetime import datetime,timezone
from ops.research_integrated_fusion_v45 import history,prepare,from_root
from ops.research_prospective_fusion_v38 import replay,sha
from ops.tests.test_research_archive_score_recovery_v14 import fixture,encode
from ops.tests.test_research_two_publisher_recovery_v15 import secondary
from ops.tests.test_research_private_propline_v43 import fixture as market_fixture,NOW

def inputs():
    raw,p=fixture();s=secondary()
    return raw,[("p",encode(p))],[("s",encode(s))]
def private():
    return [{"raw":encode({"events":[market_fixture()]}),"league":"epl","captured_utc":NOW.isoformat()}]
class IntegratedFusionTests(unittest.TestCase):
    def test_history_dual_later_reference(self):
        raw,p,s=inputs()
        h,r=history(raw,p,s,as_of=NOW.isoformat())
        self.assertEqual(r["history_candidates"],1)
        self.assertEqual(r["dual_publisher_candidates"],1)
        self.assertEqual(h[0][0]["source_id"],"thesportsdb")
        self.assertEqual(h[0][0]["evidence_sha256"],sha(s[0][1]))
        self.assertEqual(len(h[0][1]),2)
    def test_strict_delay(self):
        raw,p,s=inputs()
        h,r=history(raw,p,s,as_of="2026-11-02T18:01:00Z")
        self.assertEqual(h,[])
        self.assertEqual(r["excluded"]["WITHIN_24H_DELAY"],1)
    def test_conflicting_history_excluded(self):
        raw,p,s=inputs()
        d=json.loads(s[0][1]);d["sampled_fixtures"][0]["score_ft"]=[3,1]
        h,r=history(raw,p,[("s",encode(d))],as_of=NOW.isoformat())
        self.assertEqual(h,[])
    def test_private_end_to_end(self):
        raw,p,s=inputs()
        packets,r=prepare(raw,p,s,None,private(),as_of=NOW.isoformat())
        self.assertEqual(len(packets),1)
        packet=packets[0]
        self.assertEqual(replay(packet["receipt"],packet["raw_input"]),packet["receipt"])
        self.assertTrue(packet["private_only"])
        self.assertEqual(r["local_receipts"],1)
        self.assertEqual(r["external_witnesses_created"],0)
        self.assertFalse(r["publication_allowed"])
        self.assertNotIn("Arsenal",json.dumps(r))
    def test_no_market_no_receipt(self):
        raw,p,s=inputs()
        packets,r=prepare(raw,p,s,None,[],as_of=NOW.isoformat())
        self.assertEqual(packets,[])
        self.assertEqual(r["history_inventory"]["history_candidates"],1)
        self.assertEqual(r["local_receipts"],0)
    def test_actual_archive(self):
        root=Path(__file__).resolve().parents[2]
        ledger=root/"evidence/settled.json";market=root/"market/latest.json"
        before=(ledger.read_bytes(),market.read_bytes())
        packets,r=from_root(root,as_of=datetime.now(timezone.utc).isoformat())
        self.assertEqual((ledger.read_bytes(),market.read_bytes()),before)
        self.assertEqual(r["local_receipts"],len(packets))
        self.assertEqual(r["authenticated_samples"],0)
        self.assertFalse(r["training_admission"])
        print("V45_INTEGRATED_FUSION_SUMMARY "+json.dumps(r,sort_keys=True,allow_nan=False))
