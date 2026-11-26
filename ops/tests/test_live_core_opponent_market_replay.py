import unittest
from datetime import date,timedelta
from live_core_opponent_strength import forecasts
from live_core_opponent_market_replay import grade_brier,report,parse,MARKETS
from score_distribution_vnext import score_matrix
class OpponentMarketReplayTests(unittest.TestCase):
    def train(self):
        return [((date(2023,8,1)+timedelta(days=i)).isoformat(),"A","B",i%3,1) for i in range(60)]
    def test_matrices_preserve_original_forecasts(self):
        t=[("2024-08-01","A","B",1,0)]
        plain=forecasts(self.train(),t)[0]
        extra=forecasts(self.train(),t,include_matrices=True)[0]
        self.assertEqual(plain,extra[:7])
        self.assertEqual(set(extra[-1]),{"baseline","blend_50"})
    def test_exact_quarter_grade_brier(self):
        # Home win by one: -0.75 is half win, +0.25 full win.
        matrix=((0.,0.),(1.,0.))
        self.assertEqual(grade_brier(matrix,1,0,"asian_handicap","HOME",-.75),0.)
        self.assertEqual(grade_brier(matrix,0,0,"asian_handicap","HOME",-.75),2.)
        for _,market,side,line in MARKETS:
            self.assertTrue(0<=grade_brier(score_matrix(1.5,1.2),1,0,market,side,line)<=2)
    def test_same_cases_and_metric_count(self):
        r=report(self.train(),[("2024-08-01","A","B",1,0)])
        self.assertEqual(r["assessment_n"],1)
        self.assertEqual(len(r["metrics"]),9)
        for v in r["metrics"].values():
            self.assertAlmostEqual(v["baseline"]-v["blend_50"],v["baseline_minus_candidate"])
    def test_bad_pin(self):
        with self.assertRaisesRegex(ValueError,"BLOB_PIN_CHANGED"):parse(b"{}","EPL")
