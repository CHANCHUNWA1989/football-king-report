import copy
import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_vnext_live_evidence_cut import sample, NOW
from vnext_live_evidence_cut import cut_digest
from vnext_live_auto_audit import audit_batch, _unique

def row():
    e,s=sample()
    return {"envelope":e,"snapshot":s,"expected_digest":cut_digest(e,s)}

class LiveAutoTests(unittest.TestCase):
    def test_batch_valid_but_never_certified(self):
        out=audit_batch({"cases":[row()]},NOW)
        self.assertEqual(out["structurally_consistent"],1)
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(out["production_recommendations"],"DISABLED")
        self.assertFalse(out["positive_ev_verified"])
        self.assertIsNone(out["model_edge"])
    def test_stale_and_missing(self):
        self.assertEqual(audit_batch({"cases":[row()]},NOW+120)["structurally_consistent"],0)
        self.assertEqual(audit_batch({"cases":[]},NOW)["reason"],"NO_INPUT")
    def test_duplicates_never_selected(self):
        item=row()
        out=audit_batch({"cases":[item,copy.deepcopy(item)]},NOW)
        self.assertEqual(out["rejection_counts"],{"DUPLICATE_FIXTURE":2})
        self.assertEqual(out["structurally_consistent"],0)
    def test_tamper_and_malformed(self):
        item=row()
        item["snapshot"]["quote"]["decimal_price"]=2.1
        out=audit_batch({"cases":[item,None]},NOW)
        self.assertEqual(out["rejection_counts"],{"EVIDENCE_CUT_REJECTED":1,"INVALID_CASE":1})
        self.assertFalse(out["source_authenticated"])
    def test_batch_limits(self):
        for p in (None,{},{"cases":[None]*101}):
            self.assertEqual(audit_batch(p,NOW)["reason"],"INVALID_BATCH")
        self.assertEqual(audit_batch({"cases":[]},True)["reason"],"INVALID_BATCH")
    def test_duplicate_json_keys(self):
        with self.assertRaises(ValueError):
            _unique([("cases",[]),("cases",[])])
