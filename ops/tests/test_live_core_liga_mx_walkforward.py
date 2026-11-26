import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from live_core_liga_mx_walkforward import compare,MODELS


class LigaWalkforwardTests(unittest.TestCase):
    def rows(self):
        return [("2024-07-01",str(i),"B",1,0) for i in range(51)]

    def test_same_day_no_leak(self):
        r=compare(self.rows())
        for m in MODELS:
            self.assertEqual(r["models"][m]["n"],0)
            self.assertIsNone(r["models"][m]["log_loss"])

    def test_paired_assessment(self):
        r=compare(self.rows()+[("2024-07-02","A","B",0,1)])
        for m in MODELS:
            self.assertEqual(r["models"][m]["n"],1)
            self.assertGreaterEqual(r["models"][m]["log_loss"],0)
            self.assertGreaterEqual(r["models"][m]["brier"],0)
        self.assertEqual(r["status"],"HOLD")
        self.assertFalse(r["automatic_promotion"])
        self.assertEqual(r["verified_forward_sample_credit"],0)

    def test_order_invariance(self):
        rows=self.rows()+[("2024-07-02","A","B",0,1),("2024-07-02","C","D",1,0)]
        self.assertEqual(compare(rows),compare(list(reversed(rows))))

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            compare(self.rows()+self.rows()[:1])

    def test_same_day_result_does_not_change_other_forecasts(self):
        rows=self.rows()
        a=compare(rows+[("2024-07-02","A","B",0,1),("2024-07-02","C","D",1,0)])
        b=compare(rows+[("2024-07-02","A","B",0,1),("2024-07-02","C","D",3,0)])
        self.assertEqual(a,b)
