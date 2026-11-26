import unittest
from datetime import date
from ops.historical_asian_probability_replay_20261127 import realized,loss,market_losses,evaluate,LINES
from ops.live_snapshot_market_audit_20261126 import profit
from ops.live_score_challenger_20261127 import score_grid
from ops.live_unified_market_probabilities_20261127 import OUTCOMES

class AsianReplayTests(unittest.TestCase):
    def test_realized_reference(self):
        for m in range(-6,7):
            for q in range(-16,17):
                self.assertEqual(realized(m,q/4),2-round(2*profit(m,q/4,2)))
    def test_perfect_and_bad_distribution(self):
        for y in range(5):
            p={k:float(i==y) for i,k in enumerate(OUTCOMES)}
            self.assertEqual(loss(p,y),(0,0,0))
        with self.assertRaises(ValueError):
            loss(dict.fromkeys(OUTCOMES,.1),0)
    def test_deep_invariance(self):
        for mu in [(1,1),(2,.7),(.7,2)]:
            g=score_grid((0,0),*mu,0);d=score_grid((0,0),*mu,-.1)
            for f in [(0,0),(1,0),(2,1),(4,0),(0,4)]:
                b,c=market_losses(g,f),market_losses(d,f)
                for i,line in enumerate(LINES):
                    if line in (("AH",-1.75),("OU",2.75),("OU",3.25),("OU",3.75)):
                        for x,y in zip(b[i],c[i]):
                            self.assertAlmostEqual(x,y,places=10)
    def test_replay_scope(self):
        tr=[(date(2022,1,1),"A","B",(2,1)),(date(2022,1,2),"B","A",(1,1))]
        cal=[(date(2023,1,1),"A","B",(0,0))]
        te=[(date(2024,1,1),"A","B",(2,1))]
        r=evaluate(tr,cal,te)
        self.assertEqual(len(r["lines"]),11)
        self.assertFalse(r["actual_market_quotes"])
        self.assertFalse(r["positive_ev_verified"])
        with self.assertRaises(ValueError): evaluate(tr,cal,cal)

if __name__=="__main__": unittest.main()
