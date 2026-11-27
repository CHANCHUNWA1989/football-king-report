import json
import unittest
from datetime import datetime,timezone
from pathlib import Path
from ops.research_supplemental_provenance_v46 import expanded_history,verify_ref
from ops.research_integrated_fusion_v45 import from_root,prepare
from ops.research_prospective_fusion_v38 import sha,replay
from ops.research_supplemental_history_v32 import inventory
from ops.tests.test_research_supplemental_history_v32 import earlier
from ops.tests.test_research_archive_score_recovery_v14 import fixture,encode
from ops.tests.test_research_private_propline_v43 import fixture as market_fixture,NOW
def inputs():
    raw,p=fixture();_,e=earlier()
    return raw,[("base",encode(p)),("extra",encode(e))]
class SupplementalProvenanceTests(unittest.TestCase):
    def test_reference_exact_bytes(self):
        raw,p=inputs()
        h,r=expanded_history(raw,p,[],as_of=NOW.isoformat())
        self.assertEqual(r["supplemental_accepted"],1)
        self.assertEqual(r["history_candidates"],2)
        extra=[x for x in h if x[0]["fixture_id"]=="124"][0]
        self.assertEqual(extra[0]["evidence_sha256"],sha(p[1][1]))
        self.assertEqual(extra[1][0]["path"],"extra")
    def test_changed_reference_rejected(self):
        raw,p=inputs()
        r=inventory(raw,p,[],as_of=NOW.isoformat(),include_extra_references=True)["extra_references"][0]
        ref=r["references"][0]
        with self.assertRaises(ValueError):
            verify_ref(ref,r["key"],r["score"],{(ref["provider"],ref["path"],ref["decoded_sha256"]):b"{}"},NOW)
    def test_conflicting_supplemental_score(self):
        raw,p=inputs();e=json.loads(p[1][1]);e["matches"][0]["score_ft"]=[2,0]
        h,r=expanded_history(raw,p+[("conflict",encode(e))],[],as_of=NOW.isoformat())
        self.assertEqual(r["supplemental_accepted"],0)
    def test_opt_in_private_receipt(self):
        raw,p=inputs()
        b=[{"raw":encode({"events":[market_fixture()]}),"league":"epl","captured_utc":NOW.isoformat()}]
        packets,r=prepare(raw,p,[],None,b,as_of=NOW.isoformat(),include_supplemental=True)
        self.assertEqual(r["history_inventory"]["history_candidates"],2)
        self.assertEqual(len(packets),1)
        self.assertEqual(replay(packets[0]["receipt"],packets[0]["raw_input"]),packets[0]["receipt"])
        self.assertFalse(r["publication_allowed"])
    def test_actual_archive(self):
        root=Path(__file__).resolve().parents[2]
        ledger=root/"evidence/settled.json";market=root/"market/latest.json"
        before=(ledger.read_bytes(),market.read_bytes())
        packets,r=from_root(root,as_of=datetime.now(timezone.utc).isoformat(),include_supplemental=True)
        self.assertEqual((ledger.read_bytes(),market.read_bytes()),before)
        self.assertTrue(r["history_inventory"]["reference_bytes_rechecked"])
        self.assertEqual(r["authenticated_samples"],0)
        self.assertEqual(r["local_receipts"],len(packets))
        print("V46_SUPPLEMENTAL_PROVENANCE_SUMMARY "+json.dumps(r,sort_keys=True,allow_nan=False))
