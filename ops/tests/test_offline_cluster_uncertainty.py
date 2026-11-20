"""Synthetic weekly cluster uncertainty tests."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_cluster_uncertainty import weekly_cluster_brier_uncertainty


class TestWeeklyClusterUncertainty(unittest.TestCase):
    def setUp(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.rows = []
        for i in range(350):
            kickoff = base + timedelta(days=i)
            self.rows.append({
                "event_id": f"match-{i}",
                "predicted_at_utc": (kickoff - timedelta(hours=2)).isoformat(),
                "kickoff_at_utc": kickoff.isoformat(),
                "settled_at_utc": (kickoff + timedelta(hours=3)).isoformat(),
                "probability": 0.8, "baseline_probability": 0.5, "outcome": 1,
            })

    def test_weekly_cluster_interval(self):
        result = weekly_cluster_brier_uncertainty(self.rows, repetitions=200)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["test_count"], 70)
        self.assertGreaterEqual(result["cluster_count"], 8)
        self.assertEqual(result["mean_brier_delta"], -0.21)
        self.assertEqual(result["ci95_low"], -0.21)
        self.assertEqual(result["ci95_high"], -0.21)
        self.assertFalse(result["model_validated"])

    def test_deterministic(self):
        a = weekly_cluster_brier_uncertainty(self.rows, repetitions=200, seed=7)
        b = weekly_cluster_brier_uncertainty(self.rows, repetitions=200, seed=7)
        self.assertEqual(a, b)

    def test_too_few_weeks_holds(self):
        self.assertEqual(weekly_cluster_brier_uncertainty(self.rows[:100])["status"], "HOLD")

    def test_invalid_baseline_holds(self):
        rows = [*self.rows]
        rows[-1] = {**rows[-1], "baseline_probability": 2.0}
        self.assertEqual(weekly_cluster_brier_uncertainty(rows)["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
