"""Fixed Dixon-Coles sensitivity, common-market invariants, no promotion."""
import math
import unittest
from ops.unified_shadow_integration import (
    DC_RHO_GRID, GRADES, asian_scenarios, dc_matrix, dc_sensitivity,
    distribution_from_matrix, marginal_scores, score_matrix,
)


class UnifiedDixonColesTests(unittest.TestCase):
    def test_zero_is_poisson(self):
        for h,a in ((.1,.1),(1.2,1.2),(2.1,.8),(5.5,5.5)):
            m,dc=score_matrix(h,a),dc_matrix(h,a,0.0)
            for row,other in zip(m,dc):
                for x,y in zip(row,other):
                    self.assertAlmostEqual(x,y,places=14)

    def test_low_score_formula(self):
        h,a,rho=1.7,.9,-.10
        m,dc=score_matrix(h,a),dc_matrix(h,a,rho)
        for i,j,factor in ((0,0,1-h*a*rho),(0,1,1+h*rho),
                            (1,0,1+a*rho),(1,1,1-rho)):
            self.assertAlmostEqual(dc[i][j],m[i][j]*factor,places=14)
        self.assertAlmostEqual(dc[2][1],m[2][1],places=14)

    def test_mass_and_all_markets(self):
        for h in (.1,.5,1.2,2.1,3.5,5.5):
            for a in (.1,.5,1.2,2.1,3.5,5.5):
                base=score_matrix(h,a)
                base_p=distribution_from_matrix(base,*marginal_scores(base))
                for rho in DC_RHO_GRID:
                    score=dc_matrix(h,a,rho)
                    self.assertAlmostEqual(math.fsum(map(math.fsum,score)),1,places=12)
                    self.assertTrue(all(v>=0 and math.isfinite(v) for r in score for v in r))
                    margin,total=marginal_scores(score)
                    p=distribution_from_matrix(score,margin,total)
                    self.assertAlmostEqual(p["p_home"]+p["p_draw"]+p["p_away"],1)
                    self.assertAlmostEqual(p["p_over_2_5"],base_p["p_over_2_5"],places=12)
                    self.assertAlmostEqual(p["p_under_2_5"],base_p["p_under_2_5"],places=12)
                    rows=asian_scenarios(margin,total)
                    self.assertEqual(len(rows),84)
                    for i in range(0,84,2):
                        x,y=(r["outcome_probabilities"] for r in rows[i:i+2])
                        self.assertAlmostEqual(math.fsum(x.values()),1,places=10)
                        for k,opposite in zip(GRADES,reversed(GRADES)):
                            self.assertAlmostEqual(x[k],y[opposite],places=10)

    def test_negative_rho_increases_draw_for_fixed_rates(self):
        base=score_matrix(1.2,1.2)
        other=dc_matrix(1.2,1.2,-.10)
        self.assertGreater(sum(other[i][i] for i in range(len(other))),
                           sum(base[i][i] for i in range(len(base))))

    def test_marginal_goal_means_unchanged(self):
        for rho in DC_RHO_GRID:
            m=dc_matrix(2.1,.8,rho)
            self.assertAlmostEqual(math.fsum(i*v for i,r in enumerate(m) for v in r),2.1,places=11)
            self.assertAlmostEqual(math.fsum(j*v for r in m for j,v in enumerate(r)),.8,places=11)

    def test_invalid_rho_rejected(self):
        for rho in (True,False,None,float("nan"),float("inf"),-.25,.1,"0"):
            with self.subTest(rho=rho),self.assertRaises(ValueError):
                dc_matrix(1.2,1.2,rho)

    def test_no_model_selected_or_promoted(self):
        r=dc_sensitivity(1.2,1.2)
        self.assertIsNone(r["selected_model"])
        self.assertFalse(r["independent_oos_verified"])
        self.assertEqual([s["rho"] for s in r["scenarios"]],list(DC_RHO_GRID))
        for s in r["scenarios"]:
            self.assertFalse(s["rho_fitted"])
            self.assertFalse(s["calibrated"])
            self.assertEqual(s["production_recommendations"],"DISABLED")
            self.assertEqual(s["asian_scenarios_computed"],84)
            self.assertEqual(len(s["selected_hypothetical_asian_scenarios"]),4)


if __name__=="__main__":
    unittest.main()
