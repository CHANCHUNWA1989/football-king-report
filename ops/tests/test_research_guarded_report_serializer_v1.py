import json
import unittest
from ops.research_guarded_report_serializer_v1 import serialize_guarded_research_report
from ops.research_receipt_report_projection_v1 import project_receipt_research_status

class GuardedSerializerTests(unittest.TestCase):
    def fixture(self):
        v={"offline_receipt_checks_passed":True,"transport_metadata_policy_checked":True,
           "network_request_performed":False,"tls_peer_authenticated":False,
           "checkpoint_externally_retrieved":False,"external_checkpoint_authenticated":False,
           "publisher_identity_authenticated":False,"issuer_independence_authenticated":False,
           "trusted_timestamp_verified":False,"authenticated_samples":0,
           "status":"HOLD","model_promotion_allowed":False,
           "production_recommendations":"DISABLED"}
        v["research_report"]=project_receipt_research_status(v)
        return v
    def test_canonical_export(self):
        raw=serialize_guarded_research_report(self.fixture())
        self.assertTrue(raw.endswith(b"\n"))
        self.assertEqual(json.loads(raw)["evidence_class"],"offline-integrity-only")
    def test_missing_report_rejected(self):
        v=self.fixture();del v["research_report"]
        with self.assertRaises(ValueError):serialize_guarded_research_report(v)
    def test_promoted_report_rejected(self):
        v=self.fixture();v["research_report"]["status"]="ACTIVE"
        with self.assertRaises(ValueError):serialize_guarded_research_report(v)
    def test_unverified_origin_claim_rejected(self):
        v=self.fixture();v["network_request_performed"]=True
        with self.assertRaises(ValueError):serialize_guarded_research_report(v)

if __name__=="__main__":unittest.main()
