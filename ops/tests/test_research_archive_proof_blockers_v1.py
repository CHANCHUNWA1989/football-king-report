import unittest
from ops.research_archive_proof_blockers_v1 import diagnose_archive_proof

class ArchiveProofBlockerTests(unittest.TestCase):
    def setUp(self):
        self.batch={"candidate_fixtures":75,"fresh_verified_linked_fixtures":74,
                    "authenticated_samples":0,"actual_kickoff_authenticated":False,
                    "batch_passed":False,"ledger_sha256":"a"*64}
        self.overlap={"authenticated_samples":0,"actual_kickoff_authenticated":False,
                      "upstream_independence_proven":False,"ledger_sha256":"a"*64,
                      "witness_and_two_publisher_exact_score":20}
    def test_missing_witness_is_visible(self):
        result=diagnose_archive_proof(batch=self.batch,overlap=self.overlap)
        self.assertEqual(result["missing_witnesses"],1)
        self.assertEqual(result["exact_score_corroborations"],20)
        self.assertIn("KICKOFF_NOT_AUTHENTICATED",result["blockers"])
        self.assertFalse(result["model_promotion_allowed"])
    def test_no_missing_witness_does_not_promote(self):
        self.batch["fresh_verified_linked_fixtures"]=75
        result=diagnose_archive_proof(batch=self.batch,overlap=self.overlap)
        self.assertEqual(result["missing_witnesses"],0)
        self.assertEqual(result["status"],"HOLD")
    def test_mismatched_ledgers_rejected(self):
        self.overlap["ledger_sha256"]="b"*64
        with self.assertRaises(ValueError):
            diagnose_archive_proof(batch=self.batch,overlap=self.overlap)
    def test_bool_count_rejected(self):
        self.batch["authenticated_samples"]=False
        with self.assertRaises(ValueError):
            diagnose_archive_proof(batch=self.batch,overlap=self.overlap)
if __name__=="__main__":unittest.main()
