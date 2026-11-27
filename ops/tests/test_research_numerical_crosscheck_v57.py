import copy
import unittest
from ops.tests import test_research_strict_analysis_receipt_v56 as fixture
from ops.research_strict_analysis_receipt_v56 import report
from ops.research_numerical_crosscheck_v57 import crosscheck,verify_crosscheck,DRAWS
from ops.research_unified_prematch_replay_v35 import digest

class NumericalCrosscheckV57(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        f=fixture.StrictReceiptV56()
        f.setUp()
        cls.root=f.root
        cls.record=f.record
        cls.receipt=report(f.record,root=f.root)
        cls.result=crosscheck(cls.receipt,cls.record,root=cls.root)
    def test_grid_and_sampling(self):
        r=self.result
        self.assertTrue(r["numerical_check_passed"])
        self.assertEqual(r["scenario_count"],36)
        self.assertEqual(r["total_draws"],36*DRAWS)
        self.assertEqual(len(r["diagnostics"]),36)
        for row in r["diagnostics"]:
            self.assertAlmostEqual(sum(row["exact"][k] for k in ("home","draw","away")),1)
            self.assertAlmostEqual(sum(row["sampled"][k] for k in ("home","draw","away")),1)
            self.assertLessEqual(row["max_error"],r["sampling_tolerance"])
    def test_deterministic_and_research_only(self):
        r=self.result
        self.assertTrue(verify_crosscheck(r,self.receipt,self.record,root=self.root))
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        for k in ("independent_model_validation","calibrated","training_admission",
                  "qualified_for_production","verified_executable_ev","public_output_allowed"):
            self.assertIs(r[k],False)
    def test_tampered_result_rejected(self):
        r=copy.deepcopy(self.result)
        r["diagnostics"][0]["sampled"]["home"]=1.
        r["sha256"]=digest({k:v for k,v in r.items() if k!="sha256"})
        self.assertFalse(verify_crosscheck(r,self.receipt,self.record,root=self.root))
    def test_invalid_receipt_rejected(self):
        r=copy.deepcopy(self.receipt)
        r["scenarios"][0]["home_rate"]=9.
        r["sha256"]=digest({k:v for k,v in r.items() if k!="sha256"})
        check=crosscheck(r,self.record,root=self.root)
        self.assertFalse(check["numerical_check_passed"])
        self.assertNotIn("diagnostics",check)
    def test_malformed(self):
        self.assertFalse(crosscheck({}, {},root=self.root)["numerical_check_passed"])
