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
    def test_oversized_log_rejected(self):
        with self.assertRaises(ValueError):
            audit_archive_proof_ci_log("x"*5_000_001)
if __name__=="__main__":unittest.main()
