import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from live_core_multi_league_stress import compare,paired_ci,MODELS


class MultiLeagueStressTests(unittest.TestCase):
    def rows(self):
        return [("2024-08-01",str(i),"B",1,0) for i in range(51)]

    def test_no_same_day_training(self):
        r=compare(self.rows())
        self.assertEqual(r["assessment_n"],0)
        for name in MODELS:
            self.assertIsNone(r["models"][name]["log_loss"])

    def test_common_assessment(self):
        r=compare(self.rows()+[("2024-08-02","A","B",0,1),
                              ("2024-08-10","C","D",1,0)])
        self.assertEqual(r["assessment_n"],2)
        self.assertEqual(r["weeks"],2)
        self.assertEqual(len(r["models"]),5)
        for m in r["models"].values():
            self.assertGreaterEqual(m["log_loss"],0)
            self.assertTrue(0<=m["under25_brier"]<=1)
            self.assertTrue(0<=m["under15_brier"]<=1)
        self.assertEqual(r["models"]["league_poisson"]["baseline_minus_candidate_log_loss_ci95"],[0.,0.])

    def test_order_invariant(self):
        rows=self.rows()+[("2024-08-02","A","B",0,1),("2024-08-10","C","D",1,0)]
        self.assertEqual(compare(rows),compare(list(reversed(rows))))

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            compare(self.rows()+self.rows()[:1])

    def test_constant_ci(self):
        self.assertEqual(paired_ci([(2.,2),(3.,3)],draws=200),[1.,1.])

    def test_no_single_week_ci(self):
        self.assertIsNone(paired_ci([(1.,1)]))

    def test_bootstrap_reproducible(self):
        groups=[(-1.,1),(2.,3),(5.,2)]
        self.assertEqual(paired_ci(groups),paired_ci(groups))
