import unittest
from live_core_market_family_inference import family_intervals,UNIQUE_METRICS,ALIASES,FAMILY_SIZE
class MarketFamilyTests(unittest.TestCase):
    def weekly(self,n=25):
        return {m:{(2025,i):(float(n)*.01,n) for i in range(1,13)} for m in (*UNIQUE_METRICS,*ALIASES)}
    def test_constant_delta_and_aliases(self):
        r=family_intervals(self.weekly())
        self.assertEqual(r["family_size"],36)
        self.assertEqual(len(r["positive_lower_bound_metrics"]),6)
        self.assertEqual(r["qualification_credit"],0)
        for v in r["intervals"].values():
            self.assertAlmostEqual(v[0],.01);self.assertAlmostEqual(v[1],.01)
    def test_inadequate_coverage_not_zero(self):
        r=family_intervals(self.weekly(24))
        self.assertFalse(r["descriptive_coverage_eligible"])
        self.assertTrue(all(v is None for v in r["intervals"].values()))
    def test_mismatched_alias_and_denominator_rejected(self):
        for kind in ("alias","count"):
            w=self.weekly()
            w["home_minus_025_grade_brier"][(2025,1)]=(.9,25) if kind=="alias" else (.25,24)
            with self.assertRaises(ValueError):family_intervals(w)
    def test_nonfinite_and_insufficient_draws_rejected(self):
        w=self.weekly();w["1x2_log_loss"][(2025,1)]=(float("nan"),25)
        with self.assertRaises(ValueError):family_intervals(w)
        with self.assertRaises(ValueError):family_intervals(self.weekly(),draws=100)
