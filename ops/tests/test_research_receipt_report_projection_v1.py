import unittest
from ops.research_receipt_report_projection_v1 import project_receipt_research_status

class ProjectionTests(unittest.TestCase):
    def fixture(self):
        return {"offline_receipt_checks_passed":True,
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
    def test_offline_only(self):
        self.assertEqual(project_receipt_research_status(self.fixture())["evidence_class"],"offline-integrity-only")
    def test_reject_false_authentication(self):
        for field in ("tls_peer_authenticated","publisher_identity_authenticated",
                      "trusted_timestamp_verified","network_request_performed"):
            with self.subTest(field=field):
                value=self.fixture();value[field]=True
                with self.assertRaises(ValueError):project_receipt_research_status(value)
    def test_reject_promotion(self):
        value=self.fixture();value["model_promotion_allowed"]=True
        with self.assertRaises(ValueError):project_receipt_research_status(value)
    def test_reject_missing_flags(self):
        value=self.fixture();del value["tls_peer_authenticated"]
        with self.assertRaises(ValueError):project_receipt_research_status(value)

if __name__=="__main__":unittest.main()
