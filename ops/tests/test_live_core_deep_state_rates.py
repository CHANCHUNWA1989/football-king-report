import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from live_core_deep_state_rates import fit,report

class DeepStateRateTests(unittest.TestCase):
    def setUp(self):
        self.train=[("2020-01-01","A","B",2,0,4,1),("2020-01-02","B","C",0,2,1,2),
                    ("2020-01-03","C","D",0,0,0,2)]
        self.test=[("2021-01-01","A","B",2,0,3,0),("2021-01-02","C","D",0,2,1,4),
                   ("2021-01-03","B","C",1,1,2,1)]
    def test_train_shrink_and_missing_group(self):
        pooled,groups=fit(self.train)
        self.assertEqual(pooled,(1.,1.))
        self.assertEqual(groups["HOME"]["n"],1)
        self.assertAlmostEqual(groups["HOME"]["rates"][0],52/51)
        self.assertAlmostEqual(groups["AWAY"]["rates"][1],50/51)
        p,g=fit([self.train[-1]])
        self.assertEqual(g["HOME"]["rates"],p)
    def test_equal_denominator_and_equivalent_lines(self):
        r=report(self.train,self.test)
        self.assertEqual(r["eligible_n"],2)
        self.assertEqual(r["assessment_group_counts"],{"HOME":1,"AWAY":1})
        self.assertEqual(r["by_hypothetical_line"]["-2.0"]["metrics"],r["by_hypothetical_line"]["-2.25"]["metrics"])
        self.assertEqual(r["verified_forward_sample_credit"],0)
        self.assertEqual(r["status"],"HOLD")
    def test_assessment_outcomes_cannot_change_training_rates(self):
        a=report(self.train,self.test)
        b=report(self.train,[(*r[:5],r[3]+2,r[4]+2) for r in self.test])
        self.assertEqual(a["train_groups"],b["train_groups"])
        self.assertEqual(a["eligible_n"],b["eligible_n"])
    def test_temporal_overlap_duplicate_and_empty_eligible(self):
        with self.assertRaisesRegex(ValueError,"TEMPORAL_OVERLAP"):report(self.train,self.train)
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):report(self.train,self.test+[self.test[0]])
        r=report(self.train,[self.test[-1]])
        self.assertEqual(r["eligible_n"],0)
        self.assertIsNone(r["by_hypothetical_line"]["-2.0"]["state_minus_baseline"]["brier"])
