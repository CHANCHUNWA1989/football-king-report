import hashlib
import json
import unittest
from ops.research_receipt_replay_inventory_v1 import inspect_receipt_replay

class ReceiptReplayTests(unittest.TestCase):
    def fixture(self):
        receipt=b'fixture A signed receipt'
        inventory={"schema":"football-king-receipt-replay-inventory-v1",
                   "entries":[{"fixture_key":"fixture-A","receipt_sha256":hashlib.sha256(receipt).hexdigest()}]}
        return receipt,inventory
    def pin(self,inventory):
        return hashlib.sha256(json.dumps(inventory,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    def test_valid_inventory_still_hold(self):
        receipt,inventory=self.fixture()
        result=inspect_receipt_replay("fixture-A",receipt,inventory,self.pin(inventory))
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(result["authenticated_samples"],0)
    def test_cross_fixture_replay_rejected(self):
        receipt,inventory=self.fixture()
        with self.assertRaises(ValueError):
            inspect_receipt_replay("fixture-B",receipt,inventory,self.pin(inventory))
    def test_substituted_receipt_rejected(self):
        receipt,inventory=self.fixture()
        with self.assertRaises(ValueError):
            inspect_receipt_replay("fixture-A",receipt+b'!',inventory,self.pin(inventory))
    def test_duplicate_receipt_digest_rejected(self):
        receipt,inventory=self.fixture()
        inventory["entries"].append({"fixture_key":"fixture-B","receipt_sha256":hashlib.sha256(receipt).hexdigest()})
        with self.assertRaises(ValueError):
            inspect_receipt_replay("fixture-A",receipt,inventory,self.pin(inventory))
    def test_missing_inventory_entry_rejected(self):
        receipt,inventory=self.fixture()
        inventory["entries"]=[]
        with self.assertRaises(ValueError):
            inspect_receipt_replay("fixture-A",receipt,inventory,self.pin(inventory))
    def test_wrong_inventory_pin_rejected(self):
        receipt,inventory=self.fixture()
        with self.assertRaises(ValueError):
            inspect_receipt_replay("fixture-A",receipt,inventory,"0"*64)

if __name__=="__main__":unittest.main()
