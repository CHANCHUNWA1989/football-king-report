"""Synthetic held-out evaluation tests."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_heldout_evaluation import evaluate_heldout_calibration


class TestHeldoutEvaluation(unittest.TestCase):
    def setUp(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.rows = []
        for i in range(200):
            kickoff = base + timedelta(days=i)
            self.rows.append({
                "event_id": f"match-{i}",
                "predicted_at_utc": (kickoff - timedelta(hours=2)).isoformat(),
                "kickoff_at_utc": kickoff.isoformat(),
                "settled_at_utc": (kickoff + timedelta(hours=3)).isoformat(),
                "probability": 0.8 if i >= 160 else 0.5,
                "outcome": 1 if i >= 160 else 0,
            })

    def test_only_heldout_rows_scored(self):
        result = evaluate_heldout_calibration(self.rows)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["test_count"], 40)
        self.assertEqual(result["heldout_brier_score"], 0.04)
        self.assertFalse(result["model_validated"])
        self.assertFalse(result["positive_ev_verified"])

    def test_insufficient_heldout_history_holds(self):
        self.assertEqual(evaluate_heldout_calibration(self.rows[:100])["status"], "HOLD")

    def test_duplicate_events_hold(self):
        rows = [*self.rows]
        rows[1] = {**rows[1], "event_id": rows[0]["event_id"]}
        self.assertEqual(evaluate_heldout_calibration(rows)["status"], "HOLD")

    def test_invalid_probability_holds(self):
        rows = [*self.rows]
        rows[-1] = {**rows[-1], "probability": 1.4}
        self.assertEqual(evaluate_heldout_calibration(rows)["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
