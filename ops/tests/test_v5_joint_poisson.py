import copy
import unittest
from datetime import date,timedelta
from ops.v5_joint_poisson import build,fit,parse,probability,rates

def doc(start,n):
    return {"matches":[{"date":(start+timedelta(days=i)).isoformat(),"team1":h,"team2":a,"score":[x,y]}
        for i in range(n) for h,a,x,y in (("A","B",3,0),("B","C",1,1),("C","A",0,2))]}
class JointTest(unittest.TestCase):
    def test_fit_and_normalization(self):
        t=doc(date(2024,8,1),40);m=fit(parse(t),date(2025,8,1))
        self.assertLess(m["final_objective"],m["initial_objective"])
        self.assertAlmostEqual(sum(m["attack"].values()),0)
        p=probability(rates(m,"A","B"));self.assertAlmostEqual(sum(p),1);self.assertGreater(p[0],p[2])
    def test_assessment_labels_do_not_change_predictions(self):
        t=doc(date(2024,8,1),40);a=doc(date(2025,8,1),5)
        r=build(t,a);b=copy.deepcopy(a);b["matches"][0]["score"]=[0,9]
        s=build(t,b);self.assertEqual(r["fit"],s["fit"])
        self.assertEqual([x["candidate"] for x in r["cases"]],[x["candidate"] for x in s["cases"]])
        self.assertEqual(r["production_recommendations"],"DISABLED")
    def test_overlap_duplicate_invalid(self):
        t=doc(date(2024,8,1),40)
        with self.assertRaises(ValueError):build(t,t)
        t["matches"].append(t["matches"][0])
        with self.assertRaises(ValueError):parse(t)
    def test_cancel_and_unknown(self):
        t=doc(date(2024,8,1),40)
        t["matches"].append({"date":"2024-10-01","team1":"A","team2":"B","status":"canceled"})
        m=fit(parse(t),date(2025,8,1))
        self.assertIsNone(rates(m,"A","unknown"))
    def test_sparse_and_future(self):
        with self.assertRaises(ValueError):fit(parse(doc(date(2024,8,1),1)),date(2025,8,1))
        with self.assertRaises(ValueError):fit(parse(doc(date(2024,8,1),40)),date(2024,8,1))
