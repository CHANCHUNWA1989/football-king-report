import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from live_core_deep_cross_league import summarize,COVERAGE,DISTINCT,parse

def sample():
    return {k:{"train_n":t,"assessment_n":a,"eligible_n":1,"excluded_n":a-1,
               "verified_forward_sample_credit":0,"production_recommendations":"DISABLED",
               "assessment_group_counts":{"HOME":1,"AWAY":0},
               "by_hypothetical_line":{l:{"n":1,"grades":{"FULL_WIN":1},
                  "state_minus_baseline":{"brier":-.01,"log_loss":-.02}} for l in DISTINCT}}
            for k,(t,a) in COVERAGE.items()}

class CrossLeagueTests(unittest.TestCase):
    def test_partition_not_independent_trials(self):
        r=summarize(sample())
        self.assertEqual(r["eligible_n"],3)
        self.assertEqual(r["train_n"],1002)
        self.assertEqual(r["assessment_n"],1011)
        self.assertEqual(r["direction_counts"]["both_improve"],12)
        self.assertTrue(r["no_pooled_inference"])
        self.assertEqual(r["verified_forward_sample_credit"],0)
    def test_count_and_gate_reject(self):
        for change in (lambda r:r["EPL"].update(excluded_n=0),
                       lambda r:r["EPL"].update(production_recommendations="ENABLED"),
                       lambda r:r["EPL"]["by_hypothetical_line"]["-1.5"].update(n=2)):
            r=sample();change(r)
            with self.assertRaises(ValueError):summarize(r)
    def test_wrong_source_pin_rejected(self):
        with self.assertRaisesRegex(ValueError,"BLOB_PIN_CHANGED"):parse(b"{}", "EPL","2022-23")
