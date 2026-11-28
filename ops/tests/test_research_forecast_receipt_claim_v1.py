import hashlib
import json
import unittest
from ops.research_forecast_receipt_claim_v1 import inspect_receipt_claim
from test_research_external_evidence_gate_v1 import candidate

class ReceiptClaimTests(unittest.TestCase):
    def setup_data(self):
        artifact=b'forecast artifact for receipt test'
        item=candidate()
        digest=hashlib.sha256(artifact).hexdigest()
        item["forecast_sha256"]=digest
        item["forecast_archive"]["sha256"]=digest
        item["forecast_archive"]["receipt_sha256"]=digest
        receipt={"schema":"football-king-archive-receipt-claim-v1",
                 "fixture_key":item["fixture_key"],"artifact_sha256":digest}
        return item,artifact,receipt
    def test_matching_receipt_still_hold(self):
        item,artifact,receipt=self.setup_data()
        result=inspect_receipt_claim(item,artifact,json.dumps(receipt).encode())
        self.assertTrue(result["receipt_claim_digest_matches"])
        self.assertFalse(result["receipt_signature_verified"])
        self.assertFalse(result["trusted_timestamp_verified"])
        self.assertEqual(result["authenticated_samples"],0)
        self.assertEqual(result["status"],"HOLD")
    def test_mismatched_digest_rejected(self):
        item,artifact,receipt=self.setup_data()
        receipt["artifact_sha256"]="b"*64
        with self.assertRaises(ValueError):
            inspect_receipt_claim(item,artifact,json.dumps(receipt).encode())
    def test_mismatched_fixture_rejected(self):
        item,artifact,receipt=self.setup_data()
        receipt["fixture_key"]="wrong"
        with self.assertRaises(ValueError):
            inspect_receipt_claim(item,artifact,json.dumps(receipt).encode())
    def test_duplicate_receipt_fields_rejected(self):
        item,artifact,receipt=self.setup_data()
        raw=json.dumps(receipt)[:-1]+',"fixture_key":"other"}'
        with self.assertRaises(ValueError):
            inspect_receipt_claim(item,artifact,raw.encode())
    def test_nonfinite_receipt_rejected(self):
        item,artifact,receipt=self.setup_data()
        raw=json.dumps(receipt)[:-1]+',"invalid":NaN}'
        with self.assertRaises(ValueError):
            inspect_receipt_claim(item,artifact,raw.encode())
    def test_empty_receipt_rejected(self):
        item,artifact,_=self.setup_data()
        with self.assertRaises(ValueError):
            inspect_receipt_claim(item,artifact,b'')

if __name__=="__main__":unittest.main()
