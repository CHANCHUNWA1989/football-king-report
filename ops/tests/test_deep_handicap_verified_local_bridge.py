import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deep_handicap_verified_local_bridge import assess
from deep_handicap_private_capture import _digest
from test_deep_handicap_private_capture import inputs
from test_deep_handicap_replay_bridge import fixture,FINAL

def run(s,q,r,m,o,kind="SYNTHETIC"):
    return assess(s,q,r,m,o,expected_candidate_sha256=r["candidate_sha256"],
                  as_of_utc=FINAL,data_kind=kind)

class ExactLocalBridgeTests(unittest.TestCase):
    def test_end_to_end_immutable_and_separate(self):
        s,q=inputs();r,m,o=fixture()
        before=copy.deepcopy((s,q,r,m,o))
        a=run(s,q,r,m,o)
        self.assertEqual((s,q,r,m,o),before)
        self.assertTrue(a["exact_local_replay"])
        self.assertEqual(a["evaluation"]["cohorts"]["SYNTHETIC"]["overall"]["n"],1)
        self.assertEqual(a["evaluation"]["cohorts"]["EXTERNAL_UNAUTHENTICATED"]["overall"]["n"],0)
        self.assertEqual(a["true_forward_sample_count"],0)
        self.assertFalse(a["external_witness_verified"])
    def test_rehashed_feasible_distribution_not_original_model(self):
        s,q=inputs();r,m,o=fixture()
        p=r["candidate"]["challenger"]["probabilities"]
        p["FULL_WIN"],p["FULL_LOSS"]=p["FULL_LOSS"],p["FULL_WIN"]
        r["candidate_sha256"]=_digest(r["candidate"])
        m["candidate_sha256"]=r["candidate_sha256"]
        a=run(s,q,r,m,o)
        self.assertFalse(a["exact_local_replay"])
        self.assertIsNone(a["evaluation"])
    def test_quote_mutation_and_result_conflict(self):
        s,q=inputs();r,m,o=fixture()
        q["quotes"][0]["decimal_odds"]=2.1
        self.assertFalse(run(s,q,r,m,o)["exact_local_replay"])
        s,q=inputs();o[0]["score_home"]=4
        a=run(s,q,r,m,o)
        self.assertTrue(a["exact_local_replay"])
        self.assertIsNone(a["evaluation"])
    def test_unverified_external_and_invalid_kind(self):
        s,q=inputs();r,m,o=fixture()
        a=run(s,q,r,m,o,"EXTERNAL_UNAUTHENTICATED")
        self.assertEqual(a["evaluation"]["cohorts"]["EXTERNAL_UNAUTHENTICATED"]["overall"]["n"],1)
        self.assertEqual(a["true_forward_sample_count"],0)
        self.assertIsNone(run(s,q,r,m,o,"VERIFIED")["evaluation"])
