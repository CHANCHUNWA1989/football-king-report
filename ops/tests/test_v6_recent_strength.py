import unittest
from datetime import date
from ops.v6_recent_strength import prior_rows,updated_rates,report
class RecentStrengthTests(unittest.TestCase):
    def test_prior_only(self):
        d=date(2026,11,25)
        r=[(date(2026,11,24),"a","b",1,2),(d,"a","b",3,4),(date(2026,11,26),"a","b",5,6)]
        self.assertEqual(prior_rows(r,d),r[:1])
    def test_rate_blend(self):
        self.assertEqual(updated_rates((1.,4.),(4.,1.)),(2.,2.))
        self.assertEqual(updated_rates((1.,2.),None),(1.,2.))
    def test_invalid_rate(self):
        with self.assertRaises(ValueError):updated_rates((1.,1.),(0.,2.))
    def test_no_small_sample_claim(self):
        r=[{"date":"2026-11-01","y":0,"baseline":[.6,.2,.2],"candidate":[.7,.2,.1]}]
        x=report(r,10,9)
        self.assertEqual(x["candidate_selected"]["accuracy"],1.)
        self.assertFalse(x["target60_point_with_min100"])
        self.assertEqual(x["production_recommendations"],"DISABLED")
