import unittest
from ops.v9_selective_confidence import features,choose,select,summary,reliability,lower

def row(i,y=0):
    return features({"season":"2024-25","date":"2025-02-01","y":y,
                     "ensemble":[.7,.2,.1],"v8":[.65,.2,.15]},[.7,.2,.1])
class SelectiveConfidenceTests(unittest.TestCase):
    def test_no_rule_for_weak_results(self):
        self.assertIsNone(choose([row(i,i%3) for i in range(200)]))
    def test_rule_and_coverage_denominator(self):
        a=[row(i) for i in range(150)]
        q=choose(a);self.assertIsNotNone(q)
        m=summary(select(a,q),300)
        self.assertEqual(m["coverage"],.5)
        self.assertEqual(m["correct"],150)
        self.assertLess(lower(150,150),1.)
    def test_assessment_and_early_calibration_rejected(self):
        a=[row(i) for i in range(150)]
        a[0]["date"]="2024-12-31"
        with self.assertRaisesRegex(ValueError,"SCOPE"):choose(a)
        a[0]["date"]="2025-08-01";a[0]["season"]="2025-26"
        with self.assertRaisesRegex(ValueError,"SCOPE"):choose(a)
    def test_reliability_and_empty_selection(self):
        a=[row(i) for i in range(10)]
        self.assertAlmostEqual(reliability(a)["ece"],.3)
        self.assertIsNone(summary([],10)["accuracy"])
        self.assertEqual(summary([],10)["coverage"],0)
