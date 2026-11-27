import unittest
from ops.v8_same_fixture import paired,compare
from ops.v5_ensemble_competition import NAMES

def inputs():
    a={"league":"de.1","date":"2025-11-01","home":"a","away":"b","y":0,"candidate":[.6,.2,.2]}
    b={**a,"p":{k:[.4,.3,.3] for k in NAMES}}
    return [a],[b]
class SameFixtureTests(unittest.TestCase):
    def test_hybrid(self):
        a,b=inputs();r=paired(a,b)[0]
        self.assertAlmostEqual(r["hybrid"][0],.5)
        self.assertAlmostEqual(sum(r["hybrid"]),1.)
    def test_conflict(self):
        a,b=inputs();b[0]["y"]=1
        with self.assertRaisesRegex(ValueError,"RESULT_CONFLICT"):paired(a,b)
    def test_duplicate(self):
        a,b=inputs()
        with self.assertRaises(ValueError):paired(a,b+b)
    def test_unmatched(self):
        a,b=inputs();b[0]["home"]="c"
        with self.assertRaisesRegex(ValueError,"NOT_IN_V8"):paired(a,b)
    def test_coverage(self):
        a,b=inputs();r=compare(paired(a,b),10)
        self.assertEqual(r["coverage"],.1)
        self.assertEqual(r["individual_fixed_threshold_50"]["ensemble"]["n"],0)
        self.assertEqual(r["individual_fixed_threshold_50"]["v8"]["n"],1)
        self.assertFalse(r["proper_score_gates"]["v8"])
