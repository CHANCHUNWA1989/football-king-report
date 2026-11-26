import unittest
from datetime import date
from ops.historical_elo_replay_20261127 import probabilities,_batch,elo_replay,INITIAL,EARLIER

class EloTests(unittest.TestCase):
    def test_probability_and_direction(self):
        for h in (1200,1500,1800):
            for a in (1200,1500,1800):
                p=probabilities(h,a,.6)
                self.assertAlmostEqual(sum(p),1)
                self.assertTrue(all(0<x<1 for x in p))
        self.assertGreater(probabilities(1800,1500,.6)[0],probabilities(1500,1500,.6)[0])
    def test_same_day_no_leakage(self):
        d=date(2024,1,1)
        rows=[(d,"A","B",(3,0)),(d,"A","C",(0,1))]
        ratings={}
        result=_batch(rows,ratings,.6)
        self.assertEqual(result[0][1],result[1][1])
        self.assertAlmostEqual(sum(ratings.values()),3*INITIAL)
        reverse={}
        _batch(reversed(rows),reverse,.6)
        for team in ratings:
            self.assertAlmostEqual(ratings[team],reverse[team])
    def test_next_day_update(self):
        r={}
        d=date(2024,1,1)
        p=_batch([(d,"A","B",(3,0))],r,.6)[0][1]
        q=_batch([(date(2024,1,2),"A","B",(1,0))],r,.6)[0][1]
        self.assertGreater(q[0],p[0])
    def test_season_separation(self):
        tr=[(date(2023,1,1),"A","B",(2,1)),(date(2023,1,2),"B","A",(1,1))]
        te=[(date(2024,1,1),"C","A",(0,1))]
        self.assertEqual(elo_replay(tr,te)["test"],1)
        with self.assertRaises(ValueError): elo_replay(tr,tr)
    def test_manifest(self):
        self.assertEqual(sum(v[0] for v in EARLIER.values()),1066)

if __name__=="__main__": unittest.main()
