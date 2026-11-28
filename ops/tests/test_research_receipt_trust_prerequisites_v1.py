import hashlib
import json
import unittest
from ops.research_receipt_trust_prerequisites_v1 import inspect_receipt_trust_prerequisites
from test_research_external_evidence_gate_v1 import candidate

class ReceiptTrustPrerequisiteTests(unittest.TestCase):
    def fixture(self):
        artifact=b'actual bytes to hash'
        item=candidate()
        digest=hashlib.sha256(artifact).hexdigest()
        item["forecast_sha256"]=digest
        item["forecast_archive"]["sha256"]=digest
        item["forecast_archive"]["receipt_sha256"]=digest
        receipt=json.dumps({"schema":"football-king-archive-receipt-claim-v1",
                            "fixture_key":item["fixture_key"],
                            "artifact_sha256":digest}).encode()
        policy={"schema":"football-king-receipt-trust-policy-v1",
                "issuer":"test issuer (unverified)",
                "key_id":"test-key-unverified",
                "policy_url":"https://example.org/policy"}
        return item,artifact,receipt,policy
    def test_valid_claims_remain_unauthenticated(self):
        result=inspect_receipt_trust_prerequisites(*self.fixture())
        self.assertTrue(result["trust_policy_claim_present"])
        self.assertFalse(result["signature_cryptographically_verified"])
        self.assertFalse(result["trusted_timestamp_verified"])
        self.assertEqual(result["authenticated_samples"],0)
        self.assertEqual(result["status"],"HOLD")
    def test_missing_key_id_rejected(self):
        item,artifact,receipt,policy=self.fixture()
        del policy["key_id"]
        with self.assertRaises(ValueError):
            inspect_receipt_trust_prerequisites(item,artifact,receipt,policy)
    def test_insecure_policy_url_rejected(self):
        item,artifact,receipt,policy=self.fixture()
        policy["policy_url"]="http://example.org/policy"
        with self.assertRaises(ValueError):
            inspect_receipt_trust_prerequisites(item,artifact,receipt,policy)
    def test_wrong_policy_schema_rejected(self):
        item,artifact,receipt,policy=self.fixture()
        policy["schema"]="unknown"
        with self.assertRaises(ValueError):
            inspect_receipt_trust_prerequisites(item,artifact,receipt,policy)
    def test_wrong_receipt_digest_rejected(self):
        item,artifact,receipt,policy=self.fixture()
        receipt=receipt.replace(item["forecast_sha256"].encode(),b'b'*64)
        with self.assertRaises(ValueError):
            inspect_receipt_trust_prerequisites(item,artifact,receipt,policy)

if __name__=="__main__":unittest.main()
