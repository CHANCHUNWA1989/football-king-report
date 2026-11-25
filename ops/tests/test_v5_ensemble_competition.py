import copy
import unittest
from datetime import date,timedelta
from ops.v5_ensemble_competition import NAMES,blend,dc,evaluate,weights

def rows():
    out=[]
    for start in (date(2025,9,1),date(2026,1,1)):
        for i in range(120):
            out.append({"league":"test","date":(start+timedelta(days=i)).isoformat(),
                        "home":"H","away":"A","y":i%3,"p":{k:[.4,.3,.3] for k in NAMES}})
    return out
class EnsembleTest(unittest.TestCase):
    def test_normalized(self):
        self.assertAlmostEqual(sum(dc(1.5,1.1)),1)
        for _,w in weights():self.assertAlmostEqual(sum(blend(rows()[0]["p"],w)),1)
    def test_assessment_does_not_choose_weights(self):
        a=rows();r=evaluate(a);b=copy.deepcopy(a)
        for x in b[120:]:x["y"]=0
        s=evaluate(b)
        self.assertEqual(r["selected_weights"],s["selected_weights"])
        self.assertEqual(r["development_best_single"],s["development_best_single"])
    def test_duplicate_and_missing_model(self):
        a=rows();a.append(a[0])
        with self.assertRaises(ValueError):evaluate(a)
        a=rows();del a[0]["p"][NAMES[0]]
        with self.assertRaises(ValueError):evaluate(a)
    def test_invalid_probability(self):
        a=rows();a[0]["p"][NAMES[0]]=[.9,.9,.9]
        with self.assertRaises(ValueError):evaluate(a)
    def test_hold_and_same_cases(self):
        self.assertEqual(evaluate(rows()[:10])["status"],"HOLD")
        r=evaluate(rows())
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertEqual({v["n"] for v in r["assessment_metrics"].values()},{120})
        self.assertFalse(r["prospective_validation"])
