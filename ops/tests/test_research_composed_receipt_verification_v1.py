import hashlib
import json
import unittest
from test_research_receipt_signature_ed25519_v1 import ReceiptEd25519Tests
from ops.research_composed_receipt_verification_v1 import inspect_composed_receipt

class ComposedReceiptTests(unittest.TestCase):
    def fixture(self):
        item,artifact,receipt,policy,sig,key,binding,pin=ReceiptEd25519Tests().fixture()
        registry={"schema":"football-king-trusted-key-registry-v1",
                  "keys":[{"issuer":binding["issuer"],"key_id":binding["key_id"],
                           "public_key_sha256":binding["public_key_sha256"],
                           "not_before":"2026-01-01T00:00:00Z",
                           "not_after":"2027-01-01T00:00:00Z","state":"active"}]}
        reg_pin=hashlib.sha256(json.dumps(registry,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        history={"schema":"football-king-key-revocation-history-v1","events":[]}
        history_pin=hashlib.sha256(json.dumps(history,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        replay={"schema":"football-king-receipt-replay-inventory-v1",
                "entries":[{"fixture_key":item["fixture_key"],
                            "receipt_sha256":hashlib.sha256(receipt).hexdigest()}]}
        replay_pin=hashlib.sha256(json.dumps(replay,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        previous={"schema":"football-king-receipt-replay-inventory-v1","entries":[]}
        previous_pin=hashlib.sha256(json.dumps(previous,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        return [item,artifact,receipt,policy,sig,key,binding,pin,registry,reg_pin,"2026-11-28T00:00:00Z",history,history_pin,replay,replay_pin,previous,previous_pin]
    def test_valid_offline_checks_still_hold(self):
        result=inspect_composed_receipt(*self.fixture())
        self.assertTrue(result["offline_receipt_checks_passed"])
        self.assertEqual(result["authenticated_samples"],0)
        self.assertFalse(result["trusted_timestamp_verified"])
        self.assertEqual(result["production_recommendations"],"DISABLED")
    def test_revoked_key_rejected_even_with_valid_signature(self):
        args=self.fixture()
        args[8]["keys"][0]["state"]="revoked"
        args[9]=hashlib.sha256(json.dumps(args[8],sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        with self.assertRaises(ValueError):
            inspect_composed_receipt(*args)
    def test_registry_pin_mismatch_rejected(self):
        args=self.fixture()
        args[9]="0"*64
        with self.assertRaises(ValueError):
            inspect_composed_receipt(*args)
    def test_binding_pin_mismatch_rejected(self):
        args=self.fixture()
        args[7]="0"*64
        with self.assertRaises(ValueError):
            inspect_composed_receipt(*args)
    def test_missing_revocation_history_rejected(self):
        args=self.fixture()
        with self.assertRaises(ValueError):
            inspect_composed_receipt(*args[:11])
    def test_revoked_key_rejected_in_history(self):
        args=self.fixture()
        args[11]["events"]=[{"issuer":args[6]["issuer"],"key_id":args[6]["key_id"],
                             "revoked_at":"2026-11-27T00:00:00Z","reason":"compromised"}]
        args[12]=hashlib.sha256(json.dumps(args[11],sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        with self.assertRaises(ValueError):
            inspect_composed_receipt(*args)
    def test_missing_replay_inventory_rejected(self):
        args=self.fixture()
        with self.assertRaises(ValueError):
            inspect_composed_receipt(*args[:13])
    def test_replay_inventory_substitution_rejected(self):
        args=self.fixture()
        args[13]["entries"][0]["receipt_sha256"]="0"*64
        args[14]=hashlib.sha256(json.dumps(args[13],sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        with self.assertRaises(ValueError):
            inspect_composed_receipt(*args)
    def test_missing_previous_inventory_rejected(self):
        args=self.fixture()
        with self.assertRaises(ValueError):
            inspect_composed_receipt(*args[:15])
    def test_rewritten_inventory_history_rejected(self):
        args=self.fixture()
        args[15]={"schema":"football-king-receipt-replay-inventory-v1",
                  "entries":[{"fixture_key":"older","receipt_sha256":"a"*64}]}
        args[16]=hashlib.sha256(json.dumps(args[15],sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        with self.assertRaises(ValueError):
            inspect_composed_receipt(*args)
    def test_expired_key_rejected(self):
        args=self.fixture()
        args[10]="2027-01-01T00:00:00Z"
        with self.assertRaises(ValueError):
            inspect_composed_receipt(*args)

if __name__=="__main__":unittest.main()
