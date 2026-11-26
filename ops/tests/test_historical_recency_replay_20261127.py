import unittest
from datetime import date,timedelta
from hashlib import sha1
from json import dumps
from ops.historical_recency_replay_20261127 import WeightedCounts,evaluate_rows,replay,load_regular

class RecencyTests(unittest.TestCase):
    def test_half_life(self):
        d=date(2024,1,1)
        c=WeightedCounts([1,1],180)
        c.update([(d,"A","B",(3,0))])
        self.assertAlmostEqual(c.strength("A",0,1,d+timedelta(days=180)),11.5/10.5)
        with self.assertRaises(ValueError): c.strength("A",0,1,d)
    def test_same_day_barrier(self):
        d=date(2024,1,1)
        a=[(d,"A","B",(3,0)),(d,"A","C",(0,1))]
        b=list(reversed(a))
        c=WeightedCounts([1.5,1.2],180);e=WeightedCounts([1.5,1.2],180)
        self.assertEqual(evaluate_rows(a,c),evaluate_rows(b,e))
        for x,y in zip(c.predict(d+timedelta(days=1),"A","B"),e.predict(d+timedelta(days=1),"A","B")):
            self.assertAlmostEqual(x,y)
    def test_selection_isolation(self):
        tr=[(date(2022,1,1),"A","B",(2,1)),(date(2022,1,2),"B","A",(1,1))]
        cal=[(date(2023,1,1),"A","B",(0,0))]
        a=replay(tr,cal,[(date(2024,1,1),"A","B",(0,0))])
        b=replay(tr,cal,[(date(2024,1,1),"A","B",(4,3))])
        self.assertEqual(a["selected_half_days"],b["selected_half_days"])
        self.assertEqual(a["calibration_log_loss"],b["calibration_log_loss"])
        self.assertFalse(a["positive_ev_verified"])
        with self.assertRaises(ValueError): replay(tr,cal,cal)
    def test_regular_filter(self):
        x={"date":"2024-01-01","team1":"A","team2":"B","score":{"ft":[1,0]}}
        raw=dumps({"matches":[dict(x,round="Regular, Matchday 1"),
                              dict(x,date="2024-02-01",round="Finals, Final")]}).encode()
        blob=sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest()
        self.assertEqual(len(load_regular(raw,blob,2,1)),1)
        with self.assertRaises(ValueError): load_regular(raw,blob,2,2)

if __name__=="__main__": unittest.main()
