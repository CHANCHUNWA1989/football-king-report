import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from live_core_deep_halftime_replay import report,grades,LINES
from asian_handicap_research import TYPES

class DeepHalftimeReplayTests(unittest.TestCase):
    def setUp(self):
        self.train=[("2020-01-01","A","B",0,0,1,1),("2020-01-02","C","D",1,0,3,0)]
        self.test=[("2021-01-01","A","B",2,0,2,0),("2021-01-02","C","D",0,2,0,3),
                   ("2021-01-03","B","C",0,0,4,0)]
    def test_same_fixture_denominator_and_half_loss(self):
        r=report(self.train,self.test)
        self.assertEqual(r["eligible_halftime_leader_n"],2)
        self.assertEqual(r["ineligible_halftime_state_n"],1)
        self.assertEqual(r["train_only_remaining_rates"],{"home":1.5,"away":.5})
        for line in LINES:
            d=r["by_hypothetical_line"][str(line)]
            self.assertEqual(d["n"],2)
            self.assertEqual(sum(d["observed_grade_counts"].values()),2)
        self.assertEqual(r["by_hypothetical_line"]["-2.25"]["observed_grade_counts"]["HALF_LOSS"],1)
        self.assertEqual(r["by_hypothetical_line"]["-2.25"]["observed_grade_counts"]["FULL_WIN"],1)
        self.assertFalse(r["actual_market_lines_verified"])
        self.assertEqual(r["verified_forward_sample_credit"],0)
    def test_mirror_mass_and_pace_direction(self):
        p=grades(2,0,1.5,.5,"HOME",-2.25,1.)
        q=grades(2,0,1.5,.5,"HOME",-2.25,.85)
        mirror=grades(0,2,.5,1.5,"AWAY",-2.25,.85)
        self.assertAlmostEqual(sum(q.values()),1)
        self.assertLess(q["FULL_WIN"],p["FULL_WIN"])
        for k in TYPES:self.assertAlmostEqual(q[k],mirror[k])
    def test_temporal_overlap_duplicates_and_missing_cohort(self):
        with self.assertRaisesRegex(ValueError,"TEMPORAL_OVERLAP"):
            report(self.train,self.train)
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):
            report(self.train,self.test+[self.test[0]])
        r=report(self.train,[self.test[-1]])
        self.assertEqual(r["eligible_halftime_leader_n"],0)
        self.assertIsNone(r["by_hypothetical_line"]["-2.25"]["metrics"]["baseline"]["brier"])
    def test_final_score_does_not_change_eligibility_or_training_rates(self):
        a=report(self.train,self.test)
        changed=[(*r[:5],r[3]+1,r[4]+2) for r in self.test]
        b=report(self.train,changed)
        self.assertEqual(a["eligible_halftime_leader_n"],b["eligible_halftime_leader_n"])
        self.assertEqual(a["train_only_remaining_rates"],b["train_only_remaining_rates"])
