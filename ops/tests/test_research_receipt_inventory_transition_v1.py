import hashlib
import copy
import json
import unittest
from ops.research_receipt_inventory_transition_v1 import inspect_inventory_transition

def pin(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

class InventoryTransitionTests(unittest.TestCase):
    def fixture(self):
        old={"schema":"football-king-receipt-replay-inventory-v1",
             "entries":[{"fixture_key":"A","receipt_sha256":"a"*64}]}
        new={"schema":old["schema"],"entries":copy.deepcopy(old["entries"])+[{"fixture_key":"B","receipt_sha256":"b"*64}]}
        return old,new
    def check(self,old,new):
        return inspect_inventory_transition(old,pin(old),new,pin(new))
    def test_append_only_still_hold(self):
        old,new=self.fixture()
        result=self.check(old,new)
        self.assertEqual(result["new_entries"],1)
        self.assertEqual(result["status"],"HOLD")
        self.assertFalse(result["external_checkpoint_authenticated"])
    def test_rollback_rejected(self):
        old,new=self.fixture()
        with self.assertRaises(ValueError):
            self.check(new,old)
    def test_rewrite_rejected(self):
        old,new=self.fixture()
        new["entries"][0]["receipt_sha256"]="c"*64
        with self.assertRaises(ValueError):
            self.check(old,new)
    def test_fixture_snapshots_are_independent(self):
        old,new=self.fixture()
        new["entries"][0]["receipt_sha256"]="c"*64
        self.assertEqual(old["entries"][0]["receipt_sha256"],"a"*64)
    def test_duplicate_digest_rejected(self):
        old,new=self.fixture()
        new["entries"][1]["receipt_sha256"]="a"*64
        with self.assertRaises(ValueError):
            self.check(old,new)
    def test_pin_tamper_rejected(self):
        old,new=self.fixture()
        with self.assertRaises(ValueError):
            inspect_inventory_transition(old,pin(old),new,"0"*64)
    def test_reordering_rejected(self):
        old,new=self.fixture()
        new["entries"].reverse()
        with self.assertRaises(ValueError):
            self.check(old,new)

if __name__=="__main__":unittest.main()
