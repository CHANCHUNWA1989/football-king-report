import unittest
from ops.research_receipt_report_projection_v1 import project_receipt_research_status
from ops.research_receipt_export_guard_v1 import inspect_exported_receipt_report

class ExportGuardTests(unittest.TestCase):
    def fixture(self):
        verification={"offline_receipt_checks_passed":True,
            "transport_metadata_policy_checked":True,
            "network_request_performed":False,
            "tls_peer_authenticated":False,
            "checkpoint_externally_retrieved":False,
            "external_checkpoint_authenticated":False,
            "publisher_identity_authenticated":False,
            "issuer_independence_authenticated":False,
            "trusted_timestamp_verified":False,
            "authenticated_samples":0,"status":"HOLD",
            "model_promotion_allowed":False,
            "production_recommendations":"DISABLED"}
        return verification,project_receipt_research_status(verification)
    def test_exact_export_accepted(self):
        verification,report=self.fixture()
        result=inspect_exported_receipt_report(verification,report)
        self.assertTrue(result["export_report_matches_guarded_projection"])
    def test_promotion_rejected(self):
        verification,report=self.fixture();report["status"]="ACTIVE"
        with self.assertRaises(ValueError):inspect_exported_receipt_report(verification,report)
    def test_missing_field_rejected(self):
        verification,report=self.fixture();del report["network_origin_authenticated"]
        with self.assertRaises(ValueError):inspect_exported_receipt_report(verification,report)
    def test_extra_claim_rejected(self):
        verification,report=self.fixture();report["verified_by"]="external auditor"
        with self.assertRaises(ValueError):inspect_exported_receipt_report(verification,report)

if __name__=="__main__":unittest.main()
