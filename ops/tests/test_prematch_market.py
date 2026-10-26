"""Synthetic prematch market validation and negative-path tests."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prematch_market import evaluate_prematch_market


class TestPrematchMarket(unittest.TestCase):
    def setUp(self):
        self.snapshot = {
            "fixture_id": "match-123", "provider_id": "synthetic-provider",
            "model_version": "v1", "captured_at_utc": "2026-10-24T11:00:00Z",
            "evaluated_at_utc": "2026-10-24T11:05:00Z",
            "kickoff_at_utc": "2026-10-24T12:00:00Z",
            "decimal_odds": {"home": 2.0, "draw": 3.5, "away": 4.0},
            "model_probabilities": {"home": 0.55, "draw": 0.25, "away": 0.20}}

    def test_valid_market_is_research_only(self):
        result = evaluate_prematch_market(self.snapshot)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertAlmostEqual(result["overround"], 1/2 + 1/3.5 + 1/4)
        self.assertAlmostEqual(result["expected_values"]["home"], 0.1)
        self.assertEqual(result["candidate_outcomes"], ["home"])
        self.assertFalse(result["positive_ev_verified"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_invalid_timestamps_and_metadata_hold(self):
        variants = [
            ("captured_at_utc", "2026-10-24T12:00:00Z"),
            ("captured_at_utc", "2026-10-24T11:06:00Z"),
            ("captured_at_utc", "2026-10-24T10:00:00Z"),
            ("evaluated_at_utc", "2026-10-24T12:00:00Z"),
            ("provider_id", ""), ("fixture_id", ""), ("model_version", ""),
            ("kickoff_at_utc", "bad")]
        for key, value in variants:
            with self.subTest(key=key, value=value):
                row = copy.deepcopy(self.snapshot)
                row[key] = value
                self.assertEqual(evaluate_prematch_market(row)["status"], "HOLD")

    def test_invalid_odds_and_probabilities_hold(self):
        variants = [
            ("decimal_odds", "home", 1.0),
            ("decimal_odds", "home", float("nan")),
            ("decimal_odds", "home", True),
            ("decimal_odds", "home", 1001),
            ("model_probabilities", "home", 1.1),
            ("model_probabilities", "home", float("inf")),
            ("model_probabilities", "home", True),
            ("model_probabilities", "home", 0.54)]
        for field, outcome, value in variants:
            with self.subTest(field=field, value=value):
                row = copy.deepcopy(self.snapshot)
                row[field][outcome] = value
                self.assertEqual(evaluate_prematch_market(row)["status"], "HOLD")

    def test_invalid_overround_holds(self):
        for values in [(10, 10, 10), (1.01, 1.01, 1.01)]:
            row = copy.deepcopy(self.snapshot)
            row["decimal_odds"] = dict(zip(("home", "draw", "away"), values))
            self.assertEqual(evaluate_prematch_market(row)["status"], "HOLD")

    def test_extra_outcome_holds(self):
        row = copy.deepcopy(self.snapshot)
        row["decimal_odds"]["other"] = 2
        self.assertEqual(evaluate_prematch_market(row)["status"], "HOLD")

    def test_invalid_controls_hold(self):
        for age in (True, 0, 121, 1.5):
            self.assertEqual(evaluate_prematch_market(
                self.snapshot, max_age_minutes=age)["status"], "HOLD")
        for threshold in (True, -0.1, float("nan"), 2):
            self.assertEqual(evaluate_prematch_market(
                self.snapshot, min_ev=threshold)["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
