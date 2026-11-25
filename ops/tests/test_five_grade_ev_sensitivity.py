import itertools
import math
import unittest
from ops.five_grade_ev_sensitivity import analyze, GRADES, _adverse


class FiveGradeSensitivityTests(unittest.TestCase):
    def test_half_settlement_and_break_even(self):
        p=dict(zip(GRADES,(.3,.2,.1,.1,.3)))
        r=analyze(p,2.)
        self.assertAlmostEqual(r["nominal_net_ev_per_unit"],.05)
        self.assertAlmostEqual(r["nominal_break_even_decimal_odds"],1.875)
        self.assertAlmostEqual(r["hypothetical_tv_stress"][3]["minimum_net_ev_per_unit"],-.05)
        self.assertFalse(r["positive_ev_verified"])
        self.assertIsNone(r["recommended_stake"])

    def test_greedy_bound_against_discrete_exhaustive_oracle(self):
        # Exact grid of all five-category distributions in tenths.
        choices=[v for v in itertools.product(range(11),repeat=4) if sum(v)<=10]
        choices=[(*v,10-sum(v)) for v in choices]
        for counts in ((3,2,1,1,3),(0,2,4,4,0),(1,0,0,0,9),(0,0,0,0,10)):
            p=dict(zip(GRADES,(v/10 for v in counts)))
            for odds in (1.8,2.,3.5):
                pay=dict(zip(GRADES,(odds-1,(odds-1)/2,0.,-.5,-1.)))
                for radius in (0,.1,.2):
                    expected=min(sum(v/10*pay[k] for k,v in zip(GRADES,q))
                                 for q in choices if sum(abs(x-y) for x,y in zip(q,counts))<=round(20*radius))
                    self.assertAlmostEqual(_adverse(p,pay,radius),expected,places=12)

    def test_push_and_no_win_mass(self):
        r=analyze(dict(zip(GRADES,(0.,0.,1.,0.,0.))),1.9)
        self.assertEqual(r["nominal_net_ev_per_unit"],0.)
        self.assertIsNone(r["nominal_break_even_decimal_odds"])
        self.assertAlmostEqual(r["hypothetical_tv_stress"][-1]["minimum_net_ev_per_unit"],-.1)

    def test_monotonic_worst_case(self):
        r=analyze(dict(zip(GRADES,(.02,.03,.4,.25,.3))),3.)
        values=[x["minimum_net_ev_per_unit"] for x in r["hypothetical_tv_stress"]]
        self.assertEqual(values,sorted(values,reverse=True))
        self.assertTrue(all(-1<=x<=2 for x in values))

    def test_invalid_inputs(self):
        for p,odds in (({},2.),(dict(zip(GRADES,(True,0,0,0,0))),2.),
                       (dict(zip(GRADES,(.2,.2,.2,.2,.1))),2.),
                       (dict(zip(GRADES,(.2,.2,.2,.2,.2))),float("nan"))):
            r=analyze(p,odds)
            self.assertNotIn("nominal_net_ev_per_unit",r)
            self.assertEqual(r["status"],"HOLD")


if __name__=="__main__":
    unittest.main()
