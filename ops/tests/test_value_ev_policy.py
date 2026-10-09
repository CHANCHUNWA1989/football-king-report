"""Value screening is strictly research-only until independently validated."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from value_ev_policy import evaluate, DEFAULT_MIN_DECIMAL_ODDS, DEFAULT_MIN_CONSERVATIVE_EV

class StrictValuePolicyTests(unittest.TestCase):
    def test_missing_executable_quote_must_hold(self):
        out=evaluate(.9,None,conservative_probability=.8,quote_age_seconds=5)
        self.assertEqual(out["reason"],"NO_VERIFIED_EXECUTABLE_ODDS")
        self.assertFalse(out["qualifies_for_recommendation"])

    def test_low_odds_rejected_even_if_raw_ev_positive(self):
        out=evaluate(.85,1.30,conservative_probability=.82,quote_age_seconds=10)
        self.assertEqual(out["reason"],"ODDS_BELOW_MINIMUM")
        self.assertGreater(out["raw_model_ev"],0)
        self.assertFalse(out["research_value_screen_pass"])

    def test_raw_positive_ev_with_negative_conservative_ev_rejected(self):
        out=evaluate(.62,1.85,conservative_probability=.52,quote_age_seconds=10)
        self.assertGreater(out["raw_model_ev"],0)
        self.assertEqual(out["reason"],"INSUFFICIENT_CONSERVATIVE_EV")
        self.assertLess(out["conservative_ev"],0)

    def test_high_odds_with_positive_conservative_ev_is_only_research(self):
        out=evaluate(.70,1.90,conservative_probability=.63,quote_age_seconds=20)
        self.assertEqual(out["status"],"RESEARCH_ONLY")
        self.assertTrue(out["research_value_screen_pass"])
        self.assertGreaterEqual(out["conservative_ev"],DEFAULT_MIN_CONSERVATIVE_EV)
        self.assertFalse(out["independent_calibration_authenticated"])
        self.assertFalse(out["executable_quote_authenticated"])
        self.assertFalse(out["qualifies_for_recommendation"])
        self.assertEqual(out["production_recommendations"],"DISABLED")
        self.assertIsNone(out["recommended_stake"])

    def test_stale_quote_blocks_positive_ev(self):
        out=evaluate(.80,1.90,conservative_probability=.70,quote_age_seconds=130)
        self.assertEqual(out["reason"],"MISSING_OR_STALE_QUOTE")
        self.assertFalse(out["research_value_screen_pass"])

    def test_missing_lower_bound_blocks(self):
        out=evaluate(.8,2.1,quote_age_seconds=5)
        self.assertEqual(out["reason"],"NO_VALID_CALIBRATION_LOWER_BOUND")

    def test_boolean_odds_and_probability_rejected(self):
        self.assertEqual(evaluate(.8,True)["reason"],"INVALID_DECIMAL_ODDS")
        self.assertEqual(evaluate(True,2.0)["reason"],"INVALID_PROBABILITY")

    def test_policy_thresholds_are_explicit(self):
        out=evaluate(.65,1.75,conservative_probability=.64,quote_age_seconds=5)
        self.assertEqual(out["minimum_decimal_odds"],DEFAULT_MIN_DECIMAL_ODDS)
        self.assertEqual(out["reason"],"ODDS_BELOW_MINIMUM")
        self.assertFalse(out["qualifies_for_recommendation"])

    def test_invalid_custom_policy_fails_closed(self):
        with self.assertRaises(ValueError):
            evaluate(.8,2.0,minimum_decimal_odds=1.0)
        with self.assertRaises(ValueError):
            evaluate(.8,2.0,minimum_conservative_ev=-.01)

    def test_exact_zero_ev_not_enough_for_positive_buffer(self):
        out=evaluate(.50,2.0,conservative_probability=.50,quote_age_seconds=10)
        self.assertEqual(out["reason"],"INSUFFICIENT_CONSERVATIVE_EV")

    def test_negative_and_nonfinite_price_rejected(self):
        for odds in (0,-2,float("nan"),float("inf")):
            with self.subTest(odds=odds):
                self.assertEqual(evaluate(.8,odds)["reason"],"INVALID_DECIMAL_ODDS")

if __name__=="__main__":
    unittest.main()
