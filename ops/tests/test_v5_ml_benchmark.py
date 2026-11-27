import copy
import unittest
from datetime import date,timedelta
from unittest.mock import patch
from ops.v5_ml_benchmark import build,features,metrics,split

def fixture(start,n=65):
    return {"matches":[{"date":(start+timedelta(days=i)).isoformat(),"team1":h,"team2":a,"score":s}
        for i in range(n) for h,a,s in (("A","B",[2,0]),("C","D",[1,1]),("E","F",[0,2]))]}
class MLTests(unittest.TestCase):
    def test_prior_only(self):
        a=fixture(date(2025,8,1));b=copy.deepcopy(a)
        b["matches"][-1]["score"]=[5,0]
        self.assertTrue(features(a))
        self.assertEqual([r["x"] for r in features(a)],[r["x"] for r in features(b)])
    def test_date_overlap(self):
        a=fixture(date(2025,8,1))
        with self.assertRaises(ValueError):split(a,a)
    def test_duplicate(self):
        a=fixture(date(2025,8,1));a["matches"].append(a["matches"][0])
        with self.assertRaises(ValueError):features(a)
    def test_metrics(self):
        self.assertEqual(metrics([[.8,.1,.1]],[0])["correct"],1)
        with self.assertRaises(ValueError):metrics([[.9,.9,.9]],[0])
    def test_missing_backends_are_hold(self):
        with patch("ops.v5_ml_benchmark.classifier",side_effect=ImportError):
            r=build(fixture(date(2024,8,1)),fixture(date(2025,8,1)))
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(len(r["missing_backends"]),4)
        self.assertEqual(r["production_recommendations"],"DISABLED")
    def test_all_backends_class_order_and_same_cases(self):
        class Dummy:
            classes_=[0,1,2]
            def fit(self,x,y):pass
            def predict_proba(self,x):return [[.4,.3,.3] for _ in x]
        with patch("ops.v5_ml_benchmark.classifier",return_value=Dummy()):
            r=build(fixture(date(2024,8,1)),fixture(date(2025,8,1)))
        self.assertEqual(r["status"],"RESEARCH_ONLY")
        self.assertEqual({v["n"] for v in r["metrics"].values()},{r["assessment_n"]})
        self.assertFalse(r["automatic_promotion"])
