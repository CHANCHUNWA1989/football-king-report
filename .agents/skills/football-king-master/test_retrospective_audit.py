import copy
import json
import unittest
from pathlib import Path
import retrospective_audit as a

class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=(a.ROOT/"evidence/settled.json").read_bytes()
        cls.docs=[json.loads((Path(__file__).parent/p).read_bytes()) for p in a.FILES]
    def setUp(self):
        self.d=copy.deepcopy(self.docs)
    def audit(self): return a.audit(self.raw,self.d)
    def test_real_pinned_coverage(self):
        r=self.audit()
        self.assertEqual((r["archived"],r["observed"],r["matching"],r["certified"]),(129,25,25,0))
    def test_duplicate_cross_batch(self):
        self.d[1]["observations"].append(self.d[0]["observations"][0])
        self.d[1]["matchingOutcomes"]+=1
        with self.assertRaises(ValueError): self.audit()
    def test_false_certification(self):
        self.d[0]["observations"][0]["certifiedForwardCase"]=True
        with self.assertRaises(ValueError): self.audit()
    def test_wrong_blob(self):
        self.d[0]["ledger"]["blob"]="a"*40
        with self.assertRaises(ValueError): self.audit()
    def test_original_ledger_bytes_changed(self):
        with self.assertRaises(ValueError): a.audit(self.raw+b" ",self.d)
    def test_result_tamper(self):
        self.d[0]["observations"][0]["score"]=[3,0]
        with self.assertRaises(ValueError): self.audit()
    def test_unknown_fixture(self):
        self.d[0]["observations"][0]["key"]="unknown"
        with self.assertRaises(ValueError): self.audit()
    def test_timestamp_tamper(self):
        self.d[0]["observations"][0]["forecastUtcFromLedger"]="2026-11-28T00:00:00Z"
        with self.assertRaises(ValueError): self.audit()
    def test_single_publisher(self):
        r=self.d[0]["observations"][0];r["sources"][1]=r["sources"][0]
        with self.assertRaises(ValueError): self.audit()
    def test_bad_count(self):
        self.d[0]["matchingOutcomes"]=999
        with self.assertRaises(ValueError): self.audit()
    def test_unsafe_release(self):
        self.d[0]["release"]="READY"
        with self.assertRaises(ValueError): self.audit()
    def test_no_production_authority(self):
        r=self.audit();self.assertEqual(r["release"],"HOLD");self.assertEqual(r["production_recommendations"],"DISABLED");self.assertFalse(r["sourceAuthenticityVerified"])
if __name__=="__main__": unittest.main(verbosity=2)
