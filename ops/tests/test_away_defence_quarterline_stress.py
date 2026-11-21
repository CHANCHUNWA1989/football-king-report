"""Synthetic-only regression cases for away-defence and Asian EV stress gate."""
import copy
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from away_defence_quarterline_stress import audit


def sample():
    # These are FICTIONAL test inputs, not Bournemouth/Forest match evidence.
    return {
        "fixture": {
            "event_id": "SYNTHETIC-0001", "home_id": "H",
            "away_id": "A", "kickoff_utc": "2026-11-21T15:00:00Z",
        },
        "snapshot": {
            "captured_utc": "2026-11-21T13:00:00Z",
            "source_url": "https://example.org/stats/away",
        },
        "away_defence": {
            "away_games": 5, "away_goals_conceded": 9,
            "away_clean_sheets": 0, "away_xga_total": 6.0,
        },
        "scenarios": [
            {"scenario_id": "cautious", "lambda_home": 1.2, "lambda_away": 1.4},
            {"scenario_id": "strong-home", "lambda_home": 2.8, "lambda_away": 0.7},
        ],
        "quote": {
            "market": "asian_handicap", "side": "HOME",
            "line": -0.75, "decimal_odds": 2.20,
            "updated_utc": "2026-11-21T12:59:00Z",
        },
    }


class AwayDefenceQuarterLineTests(unittest.TestCase):
    def setUp(self):
        self.item = sample()

    def test_venue_risk_not_masked_by_unrelated_season_defence(self):
        got = audit(self.item, analysis_utc="2026-11-21T13:05:00Z")
        self.assertEqual(got["status"], "HOLD")
        self.assertEqual(got["away_defence"]["away_goals_conceded_per_game"], 1.8)
        self.assertEqual(got["away_defence"]["away_xga_per_game"], 1.2)
        self.assertIn("AWAY_CONCEDING_HIGH", got["away_defence"]["risk_flags"])
        self.assertIn("AWAY_ZERO_CLEAN_SHEETS", got["away_defence"]["risk_flags"])
        self.assertTrue(got["scenarios_disagree_on_ev_sign"])
        self.assertFalse(got["validated_positive_ev"])
        self.assertFalse(got["eligible_for_betting"])
        self.assertEqual(got["production_recommendations"], "DISABLED")

    def test_no_result_input_or_postmatch_model_backfill(self):
        for key, val in (("score_ft", [2, 0]), ("result", "H"),
                         ("independently_verified", True)):
            row = copy.deepcopy(self.item)
            row[key] = val
            with self.subTest(key=key), self.assertRaises(ValueError):
                audit(row, analysis_utc="2026-11-21T13:05:00Z")

    def test_quarter_home_profits_from_exact_margin_mass(self):
        got = audit(self.item, analysis_utc="2026-11-21T13:05:00Z")
        for s in got["scenario_results"]:
            p = s["margin_probabilities"]
            self.assertAlmostEqual(sum(p.values()), 1, places=9)
            # A -0.75 yields full profit on a 2+ margin, half on exactly 1.
            expected = 1.2 * (p["home_win_2plus"] + .5*p["home_win_1"]) - (
                p["draw"] + p["away_win"])
            self.assertAlmostEqual(expected, s["quote_ev_per_unit"], places=9)

    def test_away_quarter_line_correct_opposite_settlement(self):
        row = copy.deepcopy(self.item)
        row["quote"]["side"] = "AWAY"
        row["quote"]["line"] = .75
        row["quote"]["decimal_odds"] = 2.
        got = audit(row, analysis_utc="2026-11-21T13:05:00Z")
        for s in got["scenario_results"]:
            p = s["margin_probabilities"]
            expected = p["draw"] + p["away_win"] + .5*p["home_win_1"] - p["home_win_2plus"]
            self.assertAlmostEqual(expected, s["quote_ev_per_unit"], places=9)

    def test_do_not_infer_quote_or_ah_from_1x2_market(self):
        row = copy.deepcopy(self.item)
        row["quote"]["market"] = "h2h"
        with self.assertRaises(ValueError):
            audit(row, analysis_utc="2026-11-21T13:05:00Z")
        row = copy.deepcopy(self.item)
        del row["quote"]
        got = audit(row, analysis_utc="2026-11-21T13:05:00Z")
        self.assertEqual(got["quote_status"], "NOT_SUPPLIED")
        self.assertIsNone(got["scenario_results"][0]["quote_ev_per_unit"])

    def test_avoid_future_and_postkickoff_feature_leakage(self):
        for field, value in (
            ("captured_utc", "2026-11-21T15:01:00Z"),
            ("captured_utc", "2026-11-21T14:55:00Z"),
            ("captured_utc", "2026-11-21T13:30:00Z"),
            ("captured_utc", "2026-11-21T13:00:00"),
        ):
            row = copy.deepcopy(self.item)
            row["snapshot"][field] = value
            with self.subTest(field=value), self.assertRaises(ValueError):
                audit(row, analysis_utc="2026-11-21T13:05:00Z")

    def test_reject_quote_after_analysis_or_after_snapshot(self):
        for value in ("2026-11-21T13:06:00Z", "2026-11-21T13:01:00Z",
                      "2026-11-21T15:01:00Z", "2026-11-21T12:59:00"):
            row = copy.deepcopy(self.item)
            row["quote"]["updated_utc"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                audit(row, analysis_utc="2026-11-21T13:05:00Z")

    def test_reject_stale_quotation(self):
        row = copy.deepcopy(self.item)
        row["quote"]["updated_utc"] = "2026-11-21T08:00:00Z"
        with self.assertRaisesRegex(ValueError, "STALE"):
            audit(row, analysis_utc="2026-11-21T13:05:00Z")

    def test_reject_fake_and_inconsistent_venue_stats(self):
        for key, val in (("away_games", 0), ("away_games", True),
                         ("away_goals_conceded", -1),
                         ("away_clean_sheets", 6),
                         ("away_xga_total", float("nan")),
                         ("away_xga_total", True)):
            row = copy.deepcopy(self.item)
            row["away_defence"][key] = val
            with self.subTest(key=key, val=val), self.assertRaises(ValueError):
                audit(row, analysis_utc="2026-11-21T13:05:00Z")

    def test_reject_bad_lambda_or_underidentified_one_scenario(self):
        for value in (float("nan"), -1, 0, True, 7):
            row = copy.deepcopy(self.item)
            row["scenarios"][0]["lambda_home"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                audit(row, analysis_utc="2026-11-21T13:05:00Z")
        row = copy.deepcopy(self.item)
        row["scenarios"].pop()
        with self.assertRaises(ValueError):
            audit(row, analysis_utc="2026-11-21T13:05:00Z")

    def test_reject_unverified_non_quarter_lines_and_nonsense_odds(self):
        for field, value in (("line", -.6), ("line", True),
                             ("decimal_odds", float("inf")), ("decimal_odds", True),
                             ("decimal_odds", 0.99), ("decimal_odds", 999)):
            row = copy.deepcopy(self.item)
            row["quote"][field] = value
            with self.subTest(field=field, val=value), self.assertRaises(ValueError):
                audit(row, analysis_utc="2026-11-21T13:05:00Z")

    def test_reject_any_claim_of_external_authentication(self):
        row = copy.deepcopy(self.item)
        row["snapshot"]["source_authenticated"] = True
        with self.assertRaises(ValueError):
            audit(row, analysis_utc="2026-11-21T13:05:00Z")

    def test_input_not_mutated(self):
        before = copy.deepcopy(self.item)
        audit(self.item, analysis_utc="2026-11-21T13:05:00Z")
        self.assertEqual(before, self.item)


if __name__ == "__main__":
    unittest.main()
