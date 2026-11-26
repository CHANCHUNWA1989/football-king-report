import unittest
from datetime import date,timedelta
from ops.v12_score import grid,marginal,rate,select,summarize,MODELS
from ops.v5_ensemble_competition import dc
class ScoreTests(unittest.TestCase):
    def test_normalization_and_parity(self):
        for h,a in ((.05,.05),(1.5,1.1),(8,8)):
            g=grid(h,a);self.assertAlmostEqual(sum(g),1)
            for x,y in zip(marginal(g)[0],dc(h,a)):self.assertAlmostEqual(x,y)
    def test_invalid_rate(self):
        with self.assertRaisesRegex(ValueError,"RATE"):grid(float("nan"),1.)
    def test_missing_history(self):
        z=rate((1.5,1.),{},date(2025,8,1),"A","B",1.5,1.,30)
        self.assertAlmostEqual(z[0],1.5);self.assertAlmostEqual(z[1],1.)
    def test_future(self):
        d=date(2025,8,1)
        with self.assertRaisesRegex(ValueError,"FUTURE"):rate((1.5,1.),{"A":[(d,2,1)]},d,"A","B",1.5,1.,30)
    def test_recent_decay(self):
        d=date(2025,8,1);h={"A":[(d-timedelta(days=100),0,2),(d-timedelta(days=1),5,0)]}
        self.assertGreater(rate((1.5,1.),h,d,"A","B",1.5,1.,30)[0],rate((1.5,1.),h,d,"A","B",1.5,1.,365)[0])
    def test_leakage(self):
        with self.assertRaisesRegex(ValueError,"DEVELOPMENT"):select([{"season":"2025-26","date":"2025-08-01"}]*500)
    def test_score(self):
        z=summarize(grid(1.5,1.1),1,0)
        self.assertGreater(z["score_loss"],0)
        self.assertTrue(0<=z["total_brier"]<=1)
