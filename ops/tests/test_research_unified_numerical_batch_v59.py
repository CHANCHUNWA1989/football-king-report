import copy
import unittest
from datetime import timedelta
from unittest.mock import patch
from ops.tests.test_research_unified_cutoff_v39 import record,ROOT,NOW,KICK
from ops.research_unified_numerical_batch_v59 import run,DRAWS

class NumericalBatchV59Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=record("a")
        cls.roster={"a":KICK.isoformat()}
    def check(self,ok,records=None,roster=None,cutoff=None):
        r=run(self.roster if roster is None else roster,
              [self.a] if records is None else records,
              cutoff=NOW.isoformat() if cutoff is None else cutoff,root=ROOT)
        self.assertIs(r["batch_numerical_check_passed"],ok,r)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        for k in ("public_output_allowed","source_identity_authenticated","external_timestamp_verified",
                  "training_admission","qualified_for_production","verified_executable_ev",
                  "independent_model_validation","independent_oos_proven","calibrated"):
            self.assertIs(r[k],False)
        if not ok:
            self.assertNotIn("proofs",r)
            self.assertNotIn("local_report_sha256",r)
        return r
    def test_actual_batch(self):
        r=self.check(True)
        self.assertEqual(r["fixture_count"],1)
        self.assertEqual(r["scenario_count"],36)
        self.assertEqual(r["total_draws"],36*DRAWS)
        self.assertEqual(r["proofs"][0]["record_sha256"],self.a["sha256"])
    def test_stale_and_missing(self):
        self.check(False,cutoff=(NOW+timedelta(seconds=301)).isoformat())
        self.check(False,records=[])
    def test_tampered_record(self):
        r=copy.deepcopy(self.a);r["quotes"][0]["decimal_odds"]=4
        self.check(False,records=[r])
    def test_numerical_failure(self):
        with patch("ops.research_unified_numerical_batch_v59.crosscheck",
                   return_value={"numerical_check_passed":False}):
            self.check(False)
    def test_budget_before_audit(self):
        r={"forecasts":[{}]*8}
        with patch("ops.research_unified_numerical_batch_v59.audit_batch") as audit:
            self.check(False,records=[r]*4)
            self.check(False,records=[r]*9)
            audit.assert_not_called()
    def test_receipt_permission_rejected(self):
        with patch("ops.research_unified_numerical_batch_v59.report",
                   return_value={"research_completed":True,"status":"READY",
                                 "production_recommendations":"ENABLED"}):
            self.check(False)

if __name__=="__main__":unittest.main()
