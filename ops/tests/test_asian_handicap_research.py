"""Quarter-goal settlement and fixed hypothetical handicap coverage safety."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asian_handicap_research import (
    TYPES, grade, probabilities, quarter_units, split_lines, summarize_scenario,
)


class AsianHandicapResearchTests(unittest.TestCase):
    def test_quarter_line_and_half_stake_settlements(self):
        self.assertEqual(split_lines(0.25), (0, 2))
        self.assertEqual(split_lines(-0.25), (-2, 0))
        self.assertEqual(split_lines(0.75), (2, 4))
        self.assertEqual(split_lines(-0.75), (-4, -2))
        self.assertEqual(split_lines(0), (0, 0))
        expected = [
            (1, 1, "AWAY", +.25, "HALF_WIN"),
            (1, 1, "AWAY", +.50, "FULL_WIN"),
            (1, 1, "HOME", -.25, "HALF_LOSS"),
            (1, 1, "HOME", +.25, "HALF_WIN"),
            (1, 0, "AWAY", +.25, "FULL_LOSS"),
            (0, 1, "AWAY", +.25, "FULL_WIN"),
            (1, 0, "AWAY", +.75, "HALF_LOSS"),
            (1, 0, "HOME", -.75, "HALF_WIN"),
            (1, 0, "HOME", -1, "PUSH"),
            (2, 0, "AWAY", +1.25, "FULL_LOSS"),
            (1, 0, "AWAY", +1.25, "HALF_WIN"),
            (1, 0, "HOME", -1.25, "HALF_LOSS"),
            (0, 0, "HOME", 0, "PUSH"),
        ]
        for gh, ga, side, line, wanted in expected:
            with self.subTest(gh=gh, ga=ga, side=side, line=line):
                self.assertEqual(grade(gh, ga, side, line), wanted)

    def test_bad_market_lines_and_score_rejected(self):
        for invalid in (.1, .499, .3333, "nan", "Infinity", True, [], 5.25):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    quarter_units(invalid)
        for bad in ((True, 0), (-1, 1), (2, "1"), (26, 1)):
            with self.assertRaises(ValueError):
                grade(bad[0], bad[1], "HOME", 0.25)
        with self.assertRaises(ValueError):
            grade(0, 0, "D", 0.25)

    def test_poisson_five_outcomes_are_normalized_and_payout_math(self):
        observed = probabilities(1.46, 1.36, "AWAY", +.25)
        p = observed["outcome_probabilities"]
        self.assertAlmostEqual(sum(p.values()), 1, places=5)
        self.assertAlmostEqual(p["PUSH"], 0, places=6)
        self.assertAlmostEqual(p["HALF_LOSS"], 0, places=6)
        self.assertAlmostEqual(p["FULL_WIN"] + p["HALF_WIN"] +
                               p["FULL_LOSS"], 1, places=5)
        self.assertAlmostEqual(
            observed["full_or_half_win_probability"],
            p["FULL_WIN"] + p["HALF_WIN"], places=6)
        risk = p["FULL_LOSS"] + p["HALF_LOSS"]/2
        positive = p["FULL_WIN"] + p["HALF_WIN"]/2
        self.assertAlmostEqual(
            observed["model_implied_neutral_decimal_price_not_a_quote"],
            1 + risk/positive, places=4)
        self.assertFalse(observed["positive_expected_value_verified"])
        self.assertFalse(observed["qualifies_for_betting"])
        self.assertEqual(observed["production_recommendations"], "DISABLED")

    def test_extreme_rates_still_normalize_without_fake_certification(self):
        for h, a in ((0.1, .1), (5.5, 5.5), (1.8, 0.6)):
            for line in (0, +.25, -.25, +.5, +.75, -1.0):
                outcome = probabilities(h, a, "AWAY", line)
                self.assertAlmostEqual(
                    sum(outcome["outcome_probabilities"].values()), 1, places=5)
                self.assertFalse(outcome["offered_decimal_odds_authenticated"])
                self.assertTrue(outcome["poisson_model_is_uncalibrated"])
        for rate in (0.0, float("nan"), float("inf"), 8, True):
            with self.assertRaises(ValueError):
                probabilities(rate, 1.2, "HOME", +.25)

    def test_fixed_away_quarter_scenario_not_historical_offered_bet(self):
        rows = [
            {"score_ft": [1, 0], "expected_home_goals": 1.5,
             "expected_away_goals": 1.3},
            {"score_ft": [1, 1], "expected_home_goals": 1.5,
             "expected_away_goals": 1.3},
            {"score_ft": [0, 1], "expected_home_goals": 1.5,
             "expected_away_goals": 1.3},
        ]
        out = summarize_scenario(rows, "AWAY", +.25)
        self.assertEqual(out["n"], 3)
        self.assertEqual(out["observed_grades"]["FULL_WIN"], 1)
        self.assertEqual(out["observed_grades"]["HALF_WIN"], 1)
        self.assertEqual(out["observed_grades"]["FULL_LOSS"], 1)
        self.assertAlmostEqual(out["observed_full_or_half_win_fraction"], 2/3, places=4)
        self.assertFalse(out["actual_market_lines_observed"])
        self.assertFalse(out["independent_as_of_prediction_archive_present"])
        self.assertFalse(out["bookmaker_closing_odds_available"])
        self.assertTrue(out["historical_roi_not_estimable"])
        self.assertEqual(out["production_recommendations"], "DISABLED")

    def test_no_rows_fail_closed(self):
        v = summarize_scenario([], "AWAY", .75)
        self.assertEqual(v["status"], "HOLD")
        self.assertEqual(v["n"], 0)
        self.assertFalse(v["odds_and_roi_available"])


if __name__ == "__main__":
    unittest.main()
