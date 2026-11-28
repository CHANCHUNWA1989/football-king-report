import unittest
from ops.research_archive_proof_remediation_v1 import plan_archive_proof_remediation

class ArchiveProofRemediationTests(unittest.TestCase):
    def setUp(self):
        self.batch={"candidate_fixtures":75,"fresh_verified_linked_fixtures":74,
                    "authenticated_samples":0,"actual_kickoff_authenticated":False,
                    "batch_passed":False,"ledger_sha256":"a"*64}
        self.overlap={"authenticated_samples":0,"actual_kickoff_authenticated":False,
                      "upstream_independence_proven":False,"ledger_sha256":"a"*64,
                      "witness_and_two_publisher_exact_score":20}
    def test_all_blockers_have_actionable_requirements(self):
        plan=plan_archive_proof_remediation(batch=self.batch,overlap=self.overlap)
        self.assertEqual(len(plan["tasks"]),5)
        self.assertTrue(all(t["requirement"] and t["acceptance"] for t in plan["tasks"]))
        self.assertFalse(plan["external_evidence_collected"])
        self.assertFalse(plan["model_promotion_allowed"])
    def test_full_witness_count_still_requires_other_evidence(self):
        self.batch["fresh_verified_linked_fixtures"]=75
        plan=plan_archive_proof_remediation(batch=self.batch,overlap=self.overlap)
        self.assertNotIn("MISSING_VERIFIED_WITNESS",
                         [task["blocker"] for task in plan["tasks"]])
        self.assertEqual(plan["status"],"HOLD")
    def test_forged_cross_ledger_is_rejected(self):
        self.overlap["ledger_sha256"]="b"*64
        with self.assertRaises(ValueError):
            plan_archive_proof_remediation(batch=self.batch,overlap=self.overlap)
if __name__=="__main__":unittest.main()
