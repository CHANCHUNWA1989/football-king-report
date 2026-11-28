import hashlib
import json
import unittest
from ops.research_retrieved_checkpoint_bytes_v1 import inspect_retrieved_checkpoint

def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def digest(data):
    return hashlib.sha256(data).hexdigest()

class RetrievedCheckpointTests(unittest.TestCase):
    def fixture(self):
        inventory={"schema":"football-king-receipt-replay-inventory-v1","entries":[]}
        claim={"schema":"football-king-external-checkpoint-claim-v1",
               "inventory_sha256":digest(canonical(inventory)),
               "publisher":"test publisher","locator":"https://example.org/checkpoint",
               "published_at":"2026-11-28T00:00:00Z"}
        raw=canonical(claim)
        return inventory,claim,digest(raw),raw,digest(raw)
    def test_matching_bytes_still_hold(self):
        result=inspect_retrieved_checkpoint(*self.fixture())
        self.assertTrue(result["retrieved_content_matches_claim"])
        self.assertFalse(result["retrieval_origin_authenticated"])
        self.assertFalse(result["checkpoint_externally_retrieved"])
        self.assertEqual(result["status"],"HOLD")
    def test_replaced_bytes_rejected(self):
        args=list(self.fixture())
        args[3]=b'{}'
        with self.assertRaises(ValueError):
            inspect_retrieved_checkpoint(*args)
    def test_valid_digest_but_wrong_claim_rejected(self):
        args=list(self.fixture())
        args[3]=b'{}'
        args[4]=digest(args[3])
        with self.assertRaises(ValueError):
            inspect_retrieved_checkpoint(*args)
    def test_missing_bytes_rejected(self):
        args=list(self.fixture())
        args[3]=b''
        with self.assertRaises(ValueError):
            inspect_retrieved_checkpoint(*args)
    def test_invalid_json_rejected(self):
        args=list(self.fixture())
        args[3]=b'not json'
        args[4]=digest(args[3])
        with self.assertRaises(ValueError):
            inspect_retrieved_checkpoint(*args)
    def test_duplicate_json_key_rejected(self):
        args=list(self.fixture())
        raw=args[3]
        args[3]=raw[:-1]+b',"publisher":"test publisher"}'
        args[4]=digest(args[3])
        with self.assertRaises(ValueError):
            inspect_retrieved_checkpoint(*args)
    def test_nonfinite_json_constant_rejected(self):
        args=list(self.fixture())
        args[3]=args[3][:-1]+b',"extra":NaN}'
        args[4]=digest(args[3])
        with self.assertRaises(ValueError):
            inspect_retrieved_checkpoint(*args)
    def test_extra_json_field_rejected(self):
        args=list(self.fixture())
        args[1]["unexpected"]="not allowed"
        args[2]=digest(canonical(args[1]))
        args[3]=canonical(args[1])
        args[4]=digest(args[3])
        with self.assertRaises(ValueError):
            inspect_retrieved_checkpoint(*args)
    def test_utf8_bom_rejected(self):
        args=list(self.fixture())
        args[3]=b"\\xef\\xbb\\xbf"+args[3]
        args[4]=digest(args[3])
        with self.assertRaises(ValueError):
            inspect_retrieved_checkpoint(*args)
    def test_wrong_digest_rejected(self):
        args=list(self.fixture())
        args[4]="0"*64
        with self.assertRaises(ValueError):
            inspect_retrieved_checkpoint(*args)

if __name__=="__main__":unittest.main()
