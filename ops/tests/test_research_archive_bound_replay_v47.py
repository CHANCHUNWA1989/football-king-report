import json
import unittest
from copy import deepcopy
from ops.tests.test_research_supplemental_provenance_v46 import inputs
from ops.tests.test_research_private_route_bridge_v45 import batches,target,NOW
from ops.research_archive_bound_replay_v47 import capture,replay,freeze_archive

class ArchiveBoundReplayTests(unittest.TestCase):
    def fixture(self):
        ledger,p=inputs()
        return ledger,p,[],None,batches(),target()
    def build(self,args=None,expanded=True):
        return capture(*(self.fixture() if args is None else args),as_of=NOW.isoformat(),
                       include_supplemental=expanded)
    def test_roundtrip_expanded(self):
        args=self.fixture();r,s=self.build(args)
        self.assertEqual(s["private_receipts"],1)
        self.assertEqual(s["history_candidates"],2)
        self.assertTrue(replay(r,*args))
        self.assertFalse(r["public_signer_allowed"])
        self.assertEqual(r["authenticated_samples"],0)
        self.assertNotIn("Arsenal",json.dumps(s))
        self.assertNotIn("bridge_receipt",s)
    def test_default_base(self):
        r,s=self.build(expanded=False)
        self.assertEqual(s["history_candidates"],1)
        self.assertFalse(r["include_supplemental"])
    def test_original_bytes_tampered(self):
        args=self.fixture();r,_=self.build(args)
        a=list(args);a[1]=list(a[1]);label,body=a[1][1]
        a[1][1]=(label,body+b" ")
        self.assertFalse(replay(r,*a))
        a=list(args);a[0]+=b" "
        self.assertFalse(replay(r,*a))
    def test_receipt_tamper(self):
        args=self.fixture();r,_=self.build(args)
        bad=deepcopy(r);bad["bridge_receipt"]["fusion_receipt"]["candidate"]["weight"]=.1
        self.assertFalse(replay(bad,*args))
    def test_duplicate_archive_label(self):
        a=list(self.fixture());a[1]=[a[1][0],a[1][0]]
        self.assertIsNone(self.build(a)[0])
    def test_budget(self):
        with self.assertRaises(ValueError):freeze_archive([("a",b"123")],1,2)
    def test_no_market(self):
        a=list(self.fixture());a[4]=[]
        r,s=self.build(a)
        self.assertIsNone(r)
        self.assertEqual(s["private_receipts"],0)
        self.assertEqual(s["history_candidates"],2)
    def test_invalid_mode(self):
        r,s=self.build(expanded=1)
        self.assertIsNone(r)
        self.assertEqual(s["authenticated_samples"],0)
