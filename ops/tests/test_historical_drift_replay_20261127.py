import unittest
from datetime import date
from ops.historical_drift_replay_20261127 import update_scale,replay,MANIFEST

class DriftTests(unittest.TestCase):
    def test_neutral_and_bounds(self):
        self.assertAlmostEqual(update_scale(1,4,10,10),1)
        self.assertEqual(update_scale(1,100,100,1),1.25)
        self.assertEqual(update_scale(1,100,0,1),.75)
        self.assertGreater(update_scale(1,1,3,2),1)
        self.assertLess(update_scale(1,1,1,2),1)
        with self.assertRaises(ValueError): update_scale(1,0,1,1)
    def test_same_day_isolation(self):
        tr=[(date(2020,1,1),"A","B",(2,1)),(date(2020,1,2),"B","A",(1,1))]
        d=date(2021,1,1)
        rows=[(d,"A","B",(4,0)),(d,"B","A",(0,1))]
        a=replay(tr,rows);b=replay(tr,list(reversed(rows)))
        self.assertEqual(a["metrics"][0],a["metrics"][1])
        self.assertEqual(a["correct"],b["correct"])
        self.assertAlmostEqual(a["end_scale"],b["end_scale"])
        with self.assertRaises(ValueError): replay(tr,tr)
        self.assertFalse(a["positive_ev_verified"])
    def test_next_day_update(self):
        tr=[(date(2020,1,1),"A","B",(2,1)),(date(2020,1,2),"B","A",(1,1))]
        te=[(date(2021,1,1),"A","B",(9,0)),(date(2021,1,2),"A","B",(3,1))]
        r=replay(tr,te)
        self.assertNotEqual(r["metrics"][0]["tail_p"],r["metrics"][1]["tail_p"])
    def test_manifest(self):
        self.assertEqual(sum(n*4 for _,n,_ in MANIFEST.values()),2744)

if __name__=="__main__": unittest.main()
