import hashlib
import json
import unittest
from ops.tests.test_research_evidence_overlap_v23 import fixture
from ops.model_ab import candidate as b,MODEL as BM
from ops.model_market_challenger import candidate as c,MODEL as CM
from ops.research_witnessed_model_diagnostics_v24 import diagnose,paired_day_interval

def make():
    raw,result,proof=fixture();d=json.loads(raw);r=d["samples"][0]
    r.update(ab=b(r["p"]),ab_model=BM,c=c(r["p"],r["m"]),c_model=CM)
    raw=json.dumps(d).encode();sha=hashlib.sha256(raw).hexdigest()
    result["ledger_sha256"]=proof["ledger_sha256"]=sha
    return raw,result,proof
class WitnessedDiagnosticsTests(unittest.TestCase):
    def test_paired(self):
        r=diagnose(*make())
        self.assertEqual(r["witnessed_two_publisher"]["paired"]["n"],1)
        self.assertEqual(r["authenticated_samples"],0)
        self.assertFalse(r["weights_fitted"])
    def test_conflict(self):
        raw,r,p=make();r["cases"][0]["state"]="CONFLICT_REVIEW"
        self.assertEqual(diagnose(raw,r,p)["witnessed_corroborated"]["paired"]["n"],0)
    def test_missing(self):
        r=diagnose(*fixture())
        self.assertEqual(r["witnessed_corroborated"]["missing_challenger"],1)
    def test_age(self):
        self.assertEqual(diagnose(*make())["witnessed_corroborated_market_age_le_1h"]["paired"]["n"],0)
    def test_small_sample_interval(self):
        self.assertEqual(paired_day_interval([],"p")["status"],"INSUFFICIENT_DESCRIPTIVE_SAMPLE")
