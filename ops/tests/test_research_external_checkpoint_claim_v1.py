import hashlib
import json
import unittest
from ops.research_external_checkpoint_claim_v1 import inspect_external_checkpoint

def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

class CheckpointClaimTests(unittest.TestCase):
    def fixture(self):
        inventory={"schema":"football-king-receipt-replay-inventory-v1","entries":[]}
        checkpoint={"schema":"football-king-external-checkpoint-claim-v1",
                    "inventory_sha256":digest(inventory),
                    "publisher":"example test publisher",
                    "locator":"https://example.org/checkpoints/test.json",
                    "published_at":"2026-11-28T00:00:00Z"}
        return inventory,checkpoint
    def test_matching_claim_still_hold(self):
        inventory,checkpoint=self.fixture()
        result=inspect_external_checkpoint(inventory,checkpoint,digest(checkpoint))
        self.assertEqual(result["status"],"HOLD")
        self.assertFalse(result["checkpoint_externally_retrieved"])
        self.assertEqual(result["authenticated_samples"],0)
    def test_wrong_inventory_digest_rejected(self):
        inventory,checkpoint=self.fixture()
        checkpoint["inventory_sha256"]="0"*64
        with self.assertRaises(ValueError):
            inspect_external_checkpoint(inventory,checkpoint,digest(checkpoint))
    def test_wrong_checkpoint_pin_rejected(self):
        inventory,checkpoint=self.fixture()
        with self.assertRaises(ValueError):
            inspect_external_checkpoint(inventory,checkpoint,"0"*64)
    def test_missing_publisher_rejected(self):
        inventory,checkpoint=self.fixture()
        checkpoint["publisher"]=""
        with self.assertRaises(ValueError):
            inspect_external_checkpoint(inventory,checkpoint,digest(checkpoint))
    def test_non_https_locator_rejected(self):
        inventory,checkpoint=self.fixture()
        checkpoint["locator"]="http://example.org/checkpoint"
        with self.assertRaises(ValueError):
            inspect_external_checkpoint(inventory,checkpoint,digest(checkpoint))
    def test_naive_timestamp_rejected(self):
        inventory,checkpoint=self.fixture()
        checkpoint["published_at"]="2026-11-28T00:00:00"
        with self.assertRaises(ValueError):
            inspect_external_checkpoint(inventory,checkpoint,digest(checkpoint))

if __name__=="__main__":unittest.main()
