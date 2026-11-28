import unittest
from ops.research_unified_pricing_v1 import unified_research_pricing

class UnifiedPricingTests(unittest.TestCase):
    def price(self,**kw):
        args=dict(handicap_line=-0.25,totals_line=2.5,
                  handicap_home_odds=1.92,handicap_away_odds=1.92,
                  over_odds=1.9,under_odds=1.9)
        args.update(kw)
        return unified_research_pricing(1.4,1.1,**args)
    def test_one_matrix_for_all_markets(self):
        p=self.price()
        self.assertAlmostEqual(sum(p["one_x_two"].values()),1,places=8)
        self.assertAlmostEqual(p["score_mass"],1,places=8)
        self.assertEqual(set(p["markets"]),{"handicap_home","handicap_away","totals_over","totals_under"})
    def test_dixon_coles_option(self):
        a=self.price()
        b=self.price(dc_rho=-0.1)
        self.assertNotAlmostEqual(a["one_x_two"]["draw"],b["one_x_two"]["draw"],places=6)
    def test_invalid_odds_fail_closed(self):
        with self.assertRaises(ValueError):self.price(over_odds=1.)
    def test_no_false_verified_ev(self):
        p=self.price()
        self.assertFalse(p["positive_ev_verified"])
        self.assertFalse(p["odds_verified"])
        self.assertEqual(p["production_recommendations"],"DISABLED")
    def test_tail_safe_high_rates(self):
        p=unified_research_pricing(6.,5.,handicap_line=0,totals_line=3.5,
                  handicap_home_odds=2.,handicap_away_odds=2.,over_odds=2.,under_odds=2.)
        self.assertAlmostEqual(p["score_mass"],1,places=7)
if __name__=="__main__":unittest.main()
