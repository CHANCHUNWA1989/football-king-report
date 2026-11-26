import unittest
from datetime import date,timedelta
from live_core_walkforward_strength import forecast, report, team_rates
from live_core_multi_league_stress import rates
class WalkforwardStrengthTests(unittest.TestCase):
    def train(self):
        return [((date(2020,8,1)+timedelta(days=i)).isoformat(),"A","B",i%3,1) for i in range(60)]
    def test_same_day_changes_do_not_affect_same_day_forecasts(self):
        a=[("2021-08-01","A","B",0,0),("2021-08-01","B","C",1,0),("2021-08-02","A","B",0,1)]
        b=[("2021-08-01","A","B",9,0),a[1],a[2]]
        r,s=forecast(self.train(),a),forecast(self.train(),b)
        self.assertEqual(r[0][-1],s[0][-1])
        self.assertEqual(r[1][-1],s[1][-1])
        self.assertNotEqual(r[2][-1],s[2][-1])
    def test_default_shrink_matches_existing_baseline(self):
        h=[4,6,3,0,0,0];a=[0,0,0,5,4,9]
        self.assertEqual(team_rates(h,a,1.5,1.1,8),rates(h,a,1.5,1.1))
    def test_overlap_and_duplicate_rejected(self):
        train=self.train()
        for test in ([train[-1]], [("2021-08-01","A","B",0,0)]*2):
            with self.assertRaises(ValueError):forecast(train,test)
    def test_no_selection_or_forward_credit(self):
        out=report(self.train(),[("2021-08-01","A","B",1,0)])
        self.assertEqual(len(out["models"]),6)
        self.assertIsNone(out["selected_model"])
        self.assertEqual(out["verified_forward_sample_credit"],0)
        self.assertEqual(out["production_recommendations"],"DISABLED")
