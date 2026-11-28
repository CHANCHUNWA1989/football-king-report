import unittest
from ops.research_missing_witness_locator_v1 import locate_missing_witnesses

class MissingWitnessLocatorTests(unittest.TestCase):
    def test_exact_missing_fixture(self):
        result=locate_missing_witnesses(
            candidates=[{"fixture_id":"game-3"},{"fixture_id":"game-1"},{"fixture_id":"game-2"}],
            verified_witnesses=[{"fixture_id":"game-2"},{"fixture_id":"game-1"}])
        self.assertEqual(result["missing_fixture_ids"],["game-3"])
        self.assertFalse(result["evidence_authenticated"])
        self.assertEqual(result["status"],"HOLD")
    def test_unmatched_witness_rejected(self):
        with self.assertRaises(ValueError):
            locate_missing_witnesses(candidates=[{"fixture_id":"a"}],
                                     verified_witnesses=[{"fixture_id":"b"}])
    def test_duplicate_candidate_rejected(self):
        with self.assertRaises(ValueError):
            locate_missing_witnesses(candidates=[{"fixture_id":"a"},{"fixture_id":"a"}],
                                     verified_witnesses=[])
    def test_empty_id_rejected(self):
        with self.assertRaises(ValueError):
            locate_missing_witnesses(candidates=[{"fixture_id":""}],
                                     verified_witnesses=[])
    def test_stable_inventory_hash(self):
        a=locate_missing_witnesses(candidates=[{"fixture_id":"b"},{"fixture_id":"a"}],
                                   verified_witnesses=[{"fixture_id":"a"}])
        b=locate_missing_witnesses(candidates=[{"fixture_id":"a"},{"fixture_id":"b"}],
                                   verified_witnesses=[{"fixture_id":"a"}])
        self.assertEqual(a["inventory_sha256"],b["inventory_sha256"])
if __name__=="__main__":unittest.main()
