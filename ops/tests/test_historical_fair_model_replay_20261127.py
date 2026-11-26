import unittest
from datetime import date
from ops.historical_fair_model_replay_20261127 import TeamCounts,day_predictions,replay
from ops.historical_elo_replay_20261127 import elo_replay

class FairReplayTests(unittest.TestCase):
    def test_same_date_barrier(self):
        day=date(2024,1,1)
        a=[(day,"A","B",(3,0)),(day,"A","C",(0,1))]
        b=[(day,"A","B",(0,3)),(day,"A","C",(5,0))]
        x=day_predictions(a,TeamCounts([1.5,1.2]),{},.6)
        y=day_predictions(b,TeamCounts([1.5,1.2]),{},.6)
        self.assertEqual([r[2] for r in x],[r[2] for r in y])
        for _,_,ps in x:
            for p in ps: self.assertAlmostEqual(sum(p),1)
            for j in range(3): self.assertAlmostEqual(ps[2][j],(ps[0][j]+ps[1][j])/2)
    def test_next_date_update(self):
        c=TeamCounts([1.5,1.2]);r={}
        x=day_predictions([(date(2024,1,1),"A","B",(5,0))],c,r,.6)
        y=day_predictions([(date(2024,1,2),"A","B",(1,0))],c,r,.6)
        self.assertGreater(y[0][2][0][0],x[0][2][0][0])
        self.assertGreater(y[0][2][1][0],x[0][2][1][0])
    def test_elo_consistency(self):
        tr=[(date(2023,1,1),"A","B",(2,1)),(date(2023,1,2),"B","A",(1,1))]
        te=[(date(2024,1,1),"A","B",(1,0)),(date(2024,1,2),"B","A",(0,1))]
        result=replay(tr,te);old=elo_replay(tr,te)
        self.assertEqual(result["correct"][1],old["correct"])
        for k,v in old["metrics"].items(): self.assertAlmostEqual(result["metrics"]["elo"][k],v)
        with self.assertRaises(ValueError): replay(tr,tr)

if __name__=="__main__": unittest.main()
