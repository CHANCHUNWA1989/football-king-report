"""Synthetic walk-forward validation tests."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_walkforward import evaluate_walkforward


class TestWalkforward(unittest.TestCase):
    def setUp(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.rows = []
        for i in range(180):
            kickoff = base + timedelta(days=i)
            self.rows.append({
                "event_id": f"match-{i}",
                "predicted_at_utc": (kickoff - timedelta(hours=2)).isoformat(),
                "kickoff_at_utc": kickoff.isoformat(),
                "settled_at_utc": (kickoff + timedelta(hours=3)).isoformat(),
                "probability": 0.8, "outcome": 1,
            })

    def test_multiple_disjoint_test_windows(self):
        result = evaluate_walkforward(self.rows)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertGreaterEqual(result["fold_count"], 2)
        self.assertEqual(result["mean_fold_brier"], 0.04)
        event_ids = [event for fold in result["folds"] for event in fold["test_event_ids"]]
        self.assertEqual(len(event_ids), len(set(event_ids)))
        self.assertFalse(result["model_validated"])

    def test_duplicate_event_holds(self):
        rows = [*self.rows]
        rows[1] = {**rows[1], "event_id": rows[0]["event_id"]}
        self.assertEqual(evaluate_walkforward(rows)["status"], "HOLD")

    def test_whitespace_duplicate_event_holds(self):
        rows = [*self.rows]
        rows[1] = {**rows[1], "event_id": " " + rows[0]["event_id"] + " "}
        self.assertEqual(evaluate_walkforward(rows)["status"], "HOLD")

    def test_future_prediction_holds(self):
        rows = [*self.rows]
        rows[1] = {**rows[1], "predicted_at_utc": rows[1]["settled_at_utc"]}
        self.assertEqual(evaluate_walkforward(rows)["status"], "HOLD")

    def test_insufficient_folds_holds(self):
        self.assertEqual(evaluate_walkforward(self.rows[:90])["status"], "HOLD")

    def test_invalid_probability_holds(self):
        rows = [*self.rows]
        rows[90] = {**rows[90], "probability": 3}
        self.assertEqual(evaluate_walkforward(rows)["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
