"""Synthetic Poisson cutoff regressions; never historical match outcomes."""
import math
import unittest

from poisson_tail_audit import audit
from shadow_forecast import poisson_1x2


class PoissonTailAuditTests(unittest.TestCase):
    def test_high_equal_rates_expose_legacy_draw_bias(self):
        result = audit(5.5, 5.5)
        self.assertEqual(result["status"], "HOLD")
        self.assertTrue(result["numerical_truncation_risk_flag"])
        self.assertGreater(result["legacy_excluded_mass_percent"], 2.0)
        self.assertGreater(result["max_probability_delta_percentage_points"], 0.2)
        self.assertGreater(result["legacy_1x2"][1], result["reference_1x2"][1])
        self.assertFalse(result["model_accuracy_improved_proven"])
        self.assertFalse(result["positive_ev_verified"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_asymmetric_high_goal_rates_flag_and_swap(self):
        a = audit(5.5, 3.0)
        b = audit(3.0, 5.5)
        self.assertEqual(a["status"], "HOLD")
        self.assertEqual(b["status"], "HOLD")
        self.assertAlmostEqual(a["reference_1x2"][0], b["reference_1x2"][2], places=7)
        self.assertAlmostEqual(a["reference_1x2"][1], b["reference_1x2"][1], places=7)

    def test_common_low_rates_near_original(self):
        result = audit(1.2, 0.9)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertLess(result["max_probability_delta_percentage_points"], 0.001)
        self.assertFalse(result["numerical_truncation_risk_flag"])

    def test_legacy_output_numerically_matches_frozen_function(self):
        for h, a in ((0.1, 0.1), (1.7, 1.0), (5.5, 3.0), (5.5, 5.5)):
            with self.subTest(home=h, away=a):
                old = poisson_1x2(h, a)
                report = audit(h, a)
                for value, legacy in zip(report["legacy_1x2"], old):
                    self.assertAlmostEqual(value, legacy, places=6)
                self.assertAlmostEqual(sum(report["reference_1x2"]), 1, places=6)
                self.assertFalse(report["original_frozen_forecast_modified"])

    def test_invalid_ranges_and_nonfinite_rates_rejected(self):
        for rate in (True, False, None, "2.2", float("nan"), float("inf"),
                     float("-inf"), -1, 0, 0.09, 5.51):
            with self.subTest(rate=rate):
                with self.assertRaises(ValueError):
                    audit(rate, 1.0)

    def test_invalid_threshold_rejected(self):
        for threshold in (True, None, 0, -0.2, float("nan"), float("inf"), 6):
            with self.subTest(threshold=threshold):
                with self.assertRaises(ValueError):
                    audit(1.0, 1.0, alert_delta_pp=threshold)

    def test_threshold_is_expressed_in_percentage_points(self):
        high = audit(5.5, 5.5, alert_delta_pp=0.1)
        coarse = audit(5.5, 5.5, alert_delta_pp=1.0)
        self.assertEqual(high["status"], "HOLD")
        self.assertEqual(coarse["status"], "RESEARCH_ONLY")
        self.assertEqual(coarse["production_recommendations"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
