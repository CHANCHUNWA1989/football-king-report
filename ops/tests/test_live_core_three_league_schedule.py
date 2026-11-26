import unittest
from collections import deque
from datetime import date,timedelta
from live_core_three_league_schedule import features,forecasts,report,parse_es,adjust

class ThreeLeagueScheduleTests(unittest.TestCase):
    def train(self):
        return [((date(2020,8,1)+timedelta(days=i)).isoformat(),"A","B",i%3,1) for i in range(60)]
    def test_same_day_never_enters_density_or_forecast(self):
        a=[("2021-08-01","A","C",0,1),("2021-08-01","C","B",1,0),("2021-08-03","A","C",0,1)]
        b=[("2021-08-01","A","C",8,0),a[1],a[2]]
        r,s=forecasts(self.train(),a),forecasts(self.train(),b)
        self.assertEqual(r[0][5:],s[0][5:]);self.assertEqual(r[1][5:],s[1][5:])
        self.assertEqual(r[1][5][0],None)
        self.assertEqual(r[2][5][:2],(2,2))
        self.assertNotEqual(r[2][-1],s[2][-1])
    def test_unknown_and_window_boundary(self):
        day=date(2021,8,20);prior=deque([day-timedelta(days=15),day-timedelta(days=14),day-timedelta(days=3)])
        self.assertEqual(features(prior,day),(3,2))
        self.assertEqual(features(deque(),day),(None,0))
        with self.assertRaises(ValueError):features(deque([day]),day)
    def test_penalty_direction_and_mass(self):
        self.assertEqual(adjust(2,1,True,False,.1),(1.8,1))
        rows=forecasts(self.train(),[("2021-08-01","A","C",1,0)])
        for p,u in rows[0][-1].values():
            self.assertAlmostEqual(sum(p),1);self.assertTrue(0<=u<=1)
    def test_no_selection_and_empty_subsets(self):
        r=report(self.train(),[("2021-08-01","A","C",1,0)])
        self.assertIsNone(r["selected_model"])
        self.assertEqual(r["short_rest_subset"],{"n":0,"models":{}})
        self.assertEqual(r["unknown_rest_outside_14d_or_missing"],1)
    def test_bad_pin_and_overlap(self):
        with self.assertRaisesRegex(ValueError,"BLOB_PIN_CHANGED"):parse_es(b"{}","2020-21")
        with self.assertRaises(ValueError):forecasts(self.train(),[self.train()[-1]])
