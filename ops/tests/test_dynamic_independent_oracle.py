"""Independent factorial-based oracle for dynamic goal-grid truncation.

Synthetic numerical stress, not football skill evidence. The last bucket
of the deployed research grid aliases >=14 goals. Test its known error
rather than claiming exact untruncated probabilities.
"""
import math
import unittest
from ops.dynamic_score_driven_poisson import score_grid

RATES = (.08,.1,.25,.5,1.,1.5,2.,3.,4.,5.,6.,6.5)


def mass(rate):
    return [math.exp(-rate)*rate**k/math.factorial(k) for k in range(61)]


class DynamicIndependentOracleTests(unittest.TestCase):
    def test_independent_144_grid_1x2_and_totals(self):
        for h in RATES:
            for a in RATES:
                with self.subTest(h=h,a=a):
                    ph,pa=mass(h),mass(a)
                    exact=[0.,0.,0.]
                    for i,x in enumerate(ph):
                        for j,y in enumerate(pa):
                            exact[0 if i>j else 1 if i==j else 2]+=x*y
                    out=score_grid(h,a)
                    for got,want in zip(out["p_home_draw_away"],exact):
                        self.assertLessEqual(abs(got-want),3.0e-5)
                    total=mass(h+a)
                    p_le2=math.fsum(total[:3])
                    p_eq3=total[3]
                    p_ge4=1-p_le2-p_eq3
                    overs=out["over_total_goals_settlement"]
                    for line,grade,want in (
                        ("2.5","full_win",1-p_le2),
                        ("2.75","half_win",p_eq3),
                        ("2.75","full_win",p_ge4),
                        ("3.0","push",p_eq3),
                        ("3.0","full_win",p_ge4),
                    ):
                        self.assertAlmostEqual(overs[line][grade],want,places=10)

    def test_extreme_draw_tail_is_documented_not_exact(self):
        p=mass(6.5)
        exact=math.fsum(x*x for x in p)
        got=score_grid(6.5,6.5)["p_home_draw_away"][1]
        # Known alias at the 14+ bucket; numerical bound, not a performance gate.
        expected=math.fsum(p[14:])**2-math.fsum(x*x for x in p[14:])
        self.assertAlmostEqual(got-exact,expected,places=10)
        self.assertLess(expected,3e-5)


if __name__=="__main__":
    unittest.main()
