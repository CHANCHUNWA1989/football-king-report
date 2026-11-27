import copy
import unittest
from datetime import date,timedelta
from ops.v9_bayesian_state import replay,score_grid,marginal,rate_moments,decay
from ops.v5_integration_acceptance import summary,project

def history():
    start=date(2024,8,1)
    train=[(start+timedelta(days=i),"A","B",2,1) for i in range(100)]
    start=date(2025,8,1)
    test=[(start+timedelta(days=i),"A","B",1,1) for i in range(5)]
    test.append((start+timedelta(days=4),"C","D",0,2))
    return train,test

class BayesianStateTests(unittest.TestCase):
    def test_grid_and_unified_market_mass(self):
        g=score_grid((2.,4.),(1.,5.))
        self.assertAlmostEqual(sum(g.values()),1)
        self.assertAlmostEqual(sum(summary(g)["1x2"]),1)
        for k in (("handicap","home",-.25),("totals","over",2.25)):
            self.assertAlmostEqual(sum(project(g,*k).values()),1)
        self.assertAlmostEqual(sum(marginal(5.5,3.75)),1)
        with self.assertRaises(ValueError):marginal(5.5,3.)
    def test_same_day_result_mutation_does_not_change_predictions(self):
        train,test=history()
        a=replay(train,test,"en.1","2025-26")
        test[-1]=(*test[-1][:3],8,0)
        b=replay(train,test,"en.1","2025-26")
        self.assertEqual([r["bayes"] for r in a],[r["bayes"] for r in b])
        self.assertEqual(a,replay(train,list(reversed(history()[1])),"en.1","2025-26"))
    def test_prior_match_can_update_next_prediction(self):
        train,test=history()
        a=replay(train,test,"en.1","2025-26")
        test[0]=(*test[0][:3],7,0)
        b=replay(train,test,"en.1","2025-26")
        self.assertEqual(a[0]["bayes"],b[0]["bayes"])
        self.assertNotEqual(a[1]["bayes"],b[1]["bayes"])
    def test_decay_and_invalid_scope(self):
        d=date(2025,1,1)
        self.assertEqual(decay((16.,12.,d),d+timedelta(days=180))[:2],(12.,10.))
        with self.assertRaisesRegex(ValueError,"FUTURE_STATE"):decay((8.,8.,d),d-timedelta(days=1))
        train,test=history()
        with self.assertRaisesRegex(ValueError,"INVALID_SCOPE"):replay(train,test+train,"en.1","2025-26")
        with self.assertRaisesRegex(ValueError,"INVALID_FIXTURE"):replay(train,test+test,"en.1","2025-26")
