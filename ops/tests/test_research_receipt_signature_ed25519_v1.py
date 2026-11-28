import base64
import hashlib
import json
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from ops.research_receipt_signature_ed25519_v1 import verify_receipt_ed25519
from test_research_external_evidence_gate_v1 import candidate

class ReceiptEd25519Tests(unittest.TestCase):
    def fixture(self):
        artifact=b'forecast bytes for signed receipt'
        item=candidate()
        digest=hashlib.sha256(artifact).hexdigest()
        item["forecast_sha256"]=digest
        item["forecast_archive"]["sha256"]=digest
        item["forecast_archive"]["receipt_sha256"]=digest
        receipt=json.dumps({"schema":"football-king-archive-receipt-claim-v1",
                            "fixture_key":item["fixture_key"],"artifact_sha256":digest},
                           sort_keys=True).encode()
        policy={"schema":"football-king-receipt-trust-policy-v1",
                "issuer":"test only","key_id":"test-only-key",
                "policy_url":"https://example.org/policy"}
        private=Ed25519PrivateKey.generate()
        public=private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)
        sig=base64.b64encode(private.sign(receipt)).decode()
        binding={"schema":"football-king-trusted-key-binding-v1",
                 "issuer":policy["issuer"],"key_id":policy["key_id"],
                 "public_key_sha256":hashlib.sha256(public).hexdigest()}
        pin=hashlib.sha256(json.dumps(binding,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        return item,artifact,receipt,policy,sig,base64.b64encode(public).decode(),binding,pin
    def test_valid_signature_still_hold(self):
        result=verify_receipt_ed25519(*self.fixture())
        self.assertTrue(result["signature_cryptographically_verified"])
        self.assertFalse(result["trusted_timestamp_verified"])
        self.assertEqual(result["authenticated_samples"],0)
        self.assertEqual(result["status"],"HOLD")
    def test_missing_out_of_band_binding_rejected(self):
        item,artifact,receipt,policy,sig,key,_,pin=self.fixture()
        with self.assertRaises(ValueError):
            verify_receipt_ed25519(item,artifact,receipt,policy,sig,key,None,pin)
    def test_wrong_issuer_binding_rejected(self):
        item,artifact,receipt,policy,sig,key,binding,pin=self.fixture()
        binding["issuer"]="different issuer"
        with self.assertRaises(ValueError):
            verify_receipt_ed25519(item,artifact,receipt,policy,sig,key,binding,pin)
    def test_wrong_key_id_binding_rejected(self):
        item,artifact,receipt,policy,sig,key,binding,pin=self.fixture()
        binding["key_id"]="different key"
        with self.assertRaises(ValueError):
            verify_receipt_ed25519(item,artifact,receipt,policy,sig,key,binding,pin)
    def test_missing_binding_pin_rejected(self):
        item,artifact,receipt,policy,sig,key,binding,_=self.fixture()
        with self.assertRaises(ValueError):
            verify_receipt_ed25519(item,artifact,receipt,policy,sig,key,binding)
    def test_wrong_binding_pin_rejected(self):
        item,artifact,receipt,policy,sig,key,binding,_=self.fixture()
        with self.assertRaises(ValueError):
            verify_receipt_ed25519(item,artifact,receipt,policy,sig,key,binding,"0"*64)
    def test_tampered_receipt_rejected(self):
        item,artifact,receipt,policy,sig,key,binding,pin=self.fixture()
        with self.assertRaises(ValueError):
            verify_receipt_ed25519(item,artifact,receipt+b' ',policy,sig,key,binding,pin)
    def test_wrong_trusted_key_rejected(self):
        item,artifact,receipt,policy,sig,_,binding,pin=self.fixture()
        other=Ed25519PrivateKey.generate().public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)
        with self.assertRaises(ValueError):
            verify_receipt_ed25519(item,artifact,receipt,policy,sig,
                                   base64.b64encode(other).decode(),binding,pin)
    def test_malformed_signature_rejected(self):
        item,artifact,receipt,policy,_,key,binding,pin=self.fixture()
        with self.assertRaises(ValueError):
            verify_receipt_ed25519(item,artifact,receipt,policy,"not base64!",key,binding,pin)

if __name__=="__main__":unittest.main()
