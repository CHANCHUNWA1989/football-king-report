import unittest
from ops.v6_accuracy_target import select,evaluate,summary
from ops.v5_ensemble_competition import NAMES

def cases():
    return [{"league":"de.1","date":"2025-12-01" if i<120 else "2026-01-02","home":str(i),"away":"a",
             "y":0 if i%4!=0 else 1,"base":[.75,.15,.10],"p":{k:[.75,.15,.10] for k in NAMES}} for i in range(240)]
class AccuracyTargetTests(unittest.TestCase):
    def test_development_only(self):
        with self.assertRaisesRegex(ValueError,"LEAKAGE"):select(cases())
    def test_target_no_posthoc_selection(self):
        a=cases();b=cases()
        for r in b[120:]:r["y"]=1
        x,y=evaluate(a),evaluate(b)
        self.assertEqual(x["threshold"],y["threshold"])
        self.assertTrue(x["selected_point_target_met"])
        self.assertFalse(y["selected_point_target_met"])
        self.assertFalse(x["selected_conservative_target_met"])
    def test_no_threshold_if_development_fails(self):
        a=cases()
        for r in a[:120]:r["y"]=1
        self.assertIsNone(evaluate(a)["threshold"])
    def test_coverage_and_strict_1x2(self):
        a=cases()[:120];a[0]["base"]=[.40,.35,.25]
        s=summary(a,.70)
        self.assertEqual(s["n"],119)
        self.assertEqual(s["population_n"],120)
        self.assertAlmostEqual(s["coverage"],119/120)
    def test_duplicate_rejected(self):
        a=cases()
        with self.assertRaises(ValueError):evaluate(a+[a[0]])
