import unittest
from datetime import datetime,timedelta,timezone
from ops.research_paired_oos_v1 import PairedPrediction,paired_oos_report

class PairedOOSTests(unittest.TestCase):
    def sample(self,i,verified=True):
        return PairedPrediction(str(i),datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(days=i),
          "home",{"home":0.4,"draw":0.3,"away":0.3},
          {"home":0.6,"draw":0.2,"away":0.2},verified)
    def test_paired_metrics(self):
        r=paired_oos_report([self.sample(i) for i in range(40)],minimum_samples=30)
        self.assertTrue(r["minimum_sample_met"])
        self.assertLess(r["brier"]["mean_delta"],0)
        self.assertLess(r["log_loss"]["mean_delta"],0)
        self.assertIsNotNone(r["brier"]["ci95"])
        self.assertFalse(r["qualified_for_production"])
    def test_small_sample_holds(self):
        r=paired_oos_report([self.sample(i) for i in range(3)])
        self.assertFalse(r["minimum_sample_met"])
        self.assertEqual(r["status"],"HOLD")
    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):paired_oos_report([self.sample(1),self.sample(1)])
    def test_unverified_rejected(self):
        with self.assertRaises(ValueError):paired_oos_report([self.sample(1,False)])
    def test_out_of_order_rejected(self):
        with self.assertRaises(ValueError):paired_oos_report([self.sample(2),self.sample(1)])
    def test_no_automatic_promotion(self):
        r=paired_oos_report([self.sample(i) for i in range(40)])
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertFalse(r["independent_holdout_proven"])
if __name__=="__main__":unittest.main()
