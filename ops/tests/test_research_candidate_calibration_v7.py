import json
import unittest
from ops.tests.test_research_candidate_gap_v6 import data
from ops.research_candidate_calibration_v7 import compare
from ops.model_ab import candidate as b, MODEL as B
from ops.model_market_challenger import candidate as c, MODEL as C

def sealed():
    d=data();r=d["samples"][0]
    r.update(ab=b(r["p"]),ab_model=B,c=c(r["p"],r["m"]),c_model=C)
    return d
def run(d):return compare(json.dumps(d).encode())
class CandidateCalibrationTests(unittest.TestCase):
    def test_paired(self):
        r=run(sealed())
        self.assertEqual(r["paired"]["n"],1)
        self.assertGreater(r["paired"]["models"]["A"]["delta_brier_vs_market"],0)
        self.assertEqual(r["market_age_le_6h"]["n"],0)
        self.assertEqual(r["authenticated_samples"],0)
        self.assertFalse(r["weights_fitted"])
        self.assertFalse(r["model_promotion_allowed"])
    def test_missing(self):
        r=run(data())
        self.assertEqual(r["missing_challenger_count"],1)
        self.assertEqual(r["paired"]["n"],0)
    def test_tampered(self):
        d=sealed();d["samples"][0]["c"]=[.9,.05,.05]
        r=run(d);self.assertEqual(r["invalid_challenger_count"],1)
        self.assertEqual(r["paired"]["n"],0)
    def test_age_and_bins(self):
        d=sealed();d["samples"][0]["market_utc"]="2026-11-01T13:00:00Z"
        r=run(d);self.assertEqual(r["market_age_le_1h"]["n"],1)
        for bins in r["paired"]["models"]["C"]["class_reliability"]:
            self.assertEqual(sum(x["n"] for x in bins),1)
    def test_duplicate_ledger(self):
        d=sealed();d["samples"].append(d["samples"][0]);d["n"]=2
        self.assertFalse(run(d)["structural_audit_passed"])
