"""Research-only EV payout identity tests for five Asian handicap grades.

These algebraic fixtures are NOT market observations or calibrated forecasts.
"""
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asian_handicap_research import grade, probabilities

PAYOUT = {
    "FULL_WIN": lambda o: o - 1,
    "HALF_WIN": lambda o: (o - 1) / 2,
    "PUSH": lambda o: 0,
    "HALF_LOSS": lambda o: -0.5,
    "FULL_LOSS": lambda o: -1,
}


class AsianHandicapEvGradeResearchTests(unittest.TestCase):
    def test_away_minus_three_quarter_outcomes(self):
        cases = [
            (0, 4, -2.75, "FULL_WIN"),
            (0, 3, -2.75, "HALF_WIN"),
            (0, 2, -2.75, "FULL_LOSS"),
            (0, 3, -3.0, "PUSH"),
            (0, 3, -3.25, "HALF_LOSS"),
        ]
        for home, away, line, expected in cases:
            with self.subTest(line=line, score=(home, away)):
                self.assertEqual(grade(home, away, "AWAY", line), expected)

    def test_expected_value_grade_decomposition_matches_neutral_price(self):
        for line in (-2.5, -2.75, -3, -3.25):
            with self.subTest(line=line):
                output = probabilities(1.1, 2.7, "AWAY", line)
                p = output["outcome_probabilities"]
                price = output["model_implied_neutral_decimal_price_not_a_quote"]
                self.assertIsNotNone(price)
                ev = sum(p[k] * PAYOUT[k](price) for k in PAYOUT)
                self.assertAlmostEqual(ev, 0, delta=0.00002)
                self.assertFalse(output["positive_expected_value_verified"])
                self.assertFalse(output["qualifies_for_betting"])
                self.assertEqual(output["production_recommendations"], "DISABLED")

    def test_bad_or_unauthenticated_inputs_cannot_certify_bet(self):
        for line in (-2.5, -2.75, -3, -3.25):
            result = probabilities(1.1, 2.7, "AWAY", line)
            self.assertFalse(result["offered_decimal_odds_authenticated"])
            self.assertFalse(result["offered_handicap_line_authenticated"])
            self.assertTrue(result["poisson_model_is_uncalibrated"])
        for invalid in ("-2.6", float("nan"), True):
            with self.assertRaises(ValueError):
                grade(0, 3, "AWAY", invalid)


if __name__ == "__main__":
    unittest.main()
