import unittest
from datetime import date,timedelta
from live_core_venue_bias_replay import fit,forecasts,shift,report,parse
class VenueBiasTests(unittest.TestCase):
    def train(self):
        return [((date(2020,8,1)+timedelta(days=i)).isoformat(),"A","B",i%3,1) for i in range(120)]
    def test_fit_frozen_and_same_day_scores_excluded(self):
        train=self.train()
        a=[("2021-08-01","A","B",0,1),("2021-08-01","B","C",1,0),("2021-08-02","A","B",0,1)]
        b=[("2021-08-01","A","B",8,0),a[1],a[2]]
        x,y=forecasts(train,a),forecasts(train,b)
        self.assertEqual(x[:2],y[:2]);self.assertEqual(x[0],fit(train)[0])
        self.assertEqual(x[2][0][-1],y[2][0][-1]);self.assertEqual(x[2][1][-1],y[2][1][-1])
        self.assertNotEqual(x[2][2][-1],y[2][2][-1])
    def test_shift_preserves_mass_and_bounds(self):
        for h,a in ((.1,5.5),(2.,1.),(5.5,.1)):
            x,y=shift(h,a,.1)
            self.assertAlmostEqual(x+y,h+a);self.assertTrue(.1<=x<=h and a<=y<=5.5)
    def test_bad_pin_and_overlap(self):
        with self.assertRaisesRegex(ValueError,"BLOB_PIN_CHANGED"):parse(b"{}","EPL","2022-23")
        with self.assertRaises(ValueError):forecasts(self.train(),[self.train()[-1]])
    def test_same_cases_and_no_selection(self):
        r=report(self.train(),[("2021-08-01","A","B",1,0),("2021-08-02","B","A",0,1)])
        self.assertEqual(r["assessment_n"],2);self.assertIsNone(r["selected_model"])
        for v in r["models"].values():self.assertEqual(sum(x["n"] for x in v["by_actual_outcome"].values()),2)
