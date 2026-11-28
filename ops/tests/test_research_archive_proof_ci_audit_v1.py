import json
import unittest
from ops.research_archive_proof_ci_audit_v1 import audit_archive_proof_ci_log

class ArchiveProofCiAuditTests(unittest.TestCase):
    def setUp(self):
        self.batch={"candidate_fixtures":75,"fresh_verified_linked_fixtures":74,
                    "authenticated_samples":0,"actual_kickoff_authenticated":False,
                    "batch_passed":False,"ledger_sha256":"a"*64}
        self.overlap={"authenticated_samples":0,"actual_kickoff_authenticated":False,
                      "upstream_independence_proven":False,"ledger_sha256":"a"*64,
                      "witness_and_two_publisher_exact_score":20}
    def log(self):
        return ("timestamp V22_BATCH_VERIFICATION_SUMMARY "+json.dumps(self.batch)+"\n"
                "timestamp V23_EVIDENCE_OVERLAP_SUMMARY "+json.dumps(self.overlap)+"\n")
    def test_aggregate_reports_no_invented_id(self):
        audit=audit_archive_proof_ci_log(self.log())
        self.assertEqual(audit["missing_witnesses"],1)
        self.assertIsNone(audit["missing_fixture_ids"])
        self.assertEqual(audit["fixture_id_resolution"],"REQUIRES_SOURCE_INVENTORY")
        self.assertFalse(audit["model_promotion_allowed"])
    def test_missing_summary_rejected(self):
        with self.assertRaises(ValueError):
            audit_archive_proof_ci_log("V22_BATCH_VERIFICATION_SUMMARY "+json.dumps(self.batch))
    def test_duplicate_summary_rejected(self):
        with self.assertRaises(ValueError):
            audit_archive_proof_ci_log(self.log()+self.log())
    def test_cross_ledger_mismatch_rejected(self):
        self.overlap["ledger_sha256"]="b"*64
        with self.assertRaises(ValueError):
            audit_archive_proof_ci_log(self.log())
    def test_missing_inventory_zero_verified(self):
        self.batch.update(fresh_verified_linked_fixtures=75,batch_passed=True)
        extra={"ledger_sha256":"a"*64,"missing_keys":[],"count":0,"status":"HOLD"}
        report=audit_archive_proof_ci_log(self.log()+"V22_MISSING_WITNESS_KEYS "+json.dumps(extra)+"\n")
        self.assertEqual(report["missing_fixture_ids"],[])
        self.assertEqual(report["fixture_id_resolution"],"CI_SOURCE_INVENTORY_UNAUTHENTICATED")
    def test_missing_inventory_count_mismatch_rejected(self):
        extra={"ledger_sha256":"a"*64,"missing_keys":[],"count":0,"status":"HOLD"}
        with self.assertRaises(ValueError):
            audit_archive_proof_ci_log(self.log()+"V22_MISSING_WITNESS_KEYS "+json.dumps(extra)+"\n")
    def test_v25_ledger_mismatch_rejected(self):
        extra={"ledger_sha256":"b"*64,"model_promotion_allowed":False,"independent_oos_proven":False}
        with self.assertRaises(ValueError):
            audit_archive_proof_ci_log(self.log()+"V25_WITNESSED_DIAGNOSTICS_SUMMARY "+json.dumps(extra)+"\n")
    def test_v25_descriptive_flags_required(self):
        self.overlap["witness_and_result_corroboration"]=73
        v25={"ledger_sha256":"a"*64,"model_promotion_allowed":False,
             "independent_oos_proven":False,"metrics_descriptive_only":True,
             "selection_bias_possible":True,"market_same_cutoff_proven":False,
             "weights_fitted":False,"authenticated_samples":0,
             "witnessed_corroborated":{"eligible_count":73,"paired":{"n":73,"models":{}}}}
        line=lambda v: self.log()+"V25_WITNESSED_DIAGNOSTICS_SUMMARY "+json.dumps(v)+"\n"
        report=audit_archive_proof_ci_log(line(v25))
        self.assertEqual(report["model_diagnostics"]["paired_n"],73)
        for key,value in (("metrics_descriptive_only",False),("selection_bias_possible",False),
                          ("market_same_cutoff_proven",True),("weights_fitted",True),
                          ("authenticated_samples",1)):
            with self.subTest(key=key):
                bad={**v25,key:value}
                with self.assertRaises(ValueError):
                    audit_archive_proof_ci_log(line(bad))
    def test_cross_report_authenticated_count_mismatch_rejected(self):
        self.overlap["authenticated_samples"]=1
        with self.assertRaises(ValueError):
            audit_archive_proof_ci_log(self.log())
    def test_cross_report_batch_state_mismatch_rejected(self):
        self.overlap["forecast_batch_passed"]=True
        with self.assertRaises(ValueError):
            audit_archive_proof_ci_log(self.log())
    def test_cross_report_batch_state_consistent(self):
        self.overlap["forecast_batch_passed"]=False
        self.assertEqual(audit_archive_proof_ci_log(self.log())["status"],"HOLD")
    def test_v25_paired_cohort_must_match_and_fit_corroboration(self):
        v25={"ledger_sha256":"a"*64,"model_promotion_allowed":False,
             "independent_oos_proven":False,"metrics_descriptive_only":True,
             "selection_bias_possible":True,"market_same_cutoff_proven":False,
             "weights_fitted":False,"authenticated_samples":0,
             "witnessed_corroborated":{"eligible_count":20,"paired":{"n":20,"models":{"market":{}}}}}
        self.overlap["witness_and_result_corroboration"]=20
        def run():
            return audit_archive_proof_ci_log(self.log()+"V25_WITNESSED_DIAGNOSTICS_SUMMARY "+json.dumps(v25)+"\n")
        self.assertEqual(run()["model_diagnostics"]["paired_n"],20)
        v25["witnessed_corroborated"]["paired"]["n"]=19
        with self.assertRaises(ValueError):run()
        v25["witnessed_corroborated"]["paired"]["n"]=20
        self.overlap["witness_and_result_corroboration"]=19
        with self.assertRaises(ValueError):run()
    def test_v25_requires_explicit_v23_corroborated_count(self):
        v25={"ledger_sha256":"a"*64,"model_promotion_allowed":False,
             "independent_oos_proven":False,"metrics_descriptive_only":True,
             "selection_bias_possible":True,"market_same_cutoff_proven":False,
             "weights_fitted":False,"authenticated_samples":0,
             "witnessed_corroborated":{"eligible_count":20,"paired":{"n":20,"models":{}}}}
        with self.assertRaises(ValueError):
            audit_archive_proof_ci_log(self.log()+"V25_WITNESSED_DIAGNOSTICS_SUMMARY "+json.dumps(v25)+"\n")
    def test_oversized_log_rejected(self):
        with self.assertRaises(ValueError):
            audit_archive_proof_ci_log("x"*5_000_001)
if __name__=="__main__":unittest.main()
