"""Synthetic paired bootstrap uncertainty regression tests."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_brier_uncertainty import paired_brier_uncertainty


class TestBrierUncertainty(unittest.TestCase):
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
                "probability": 0.8, "baseline_probability": 0.5, "outcome": 1,
            })

    def test_constant_advantage_exact_interval(self):
        result = paired_brier_uncertainty(self.rows, repetitions=200)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["test_count"], 40)
        self.assertEqual(result["mean_brier_delta"], -0.21)
        self.assertEqual(result["ci95_low"], -0.21)
        self.assertEqual(result["ci95_high"], -0.21)
        self.assertTrue(result["interval_excludes_zero"])
        self.assertFalse(result["model_validated"])

    def test_deterministic_seed(self):
        a = paired_brier_uncertainty(self.rows, repetitions=200, seed=42)
        b = paired_brier_uncertainty(self.rows, repetitions=200, seed=42)
        self.assertEqual(a, b)

    def test_insufficient_test_set_holds(self):
        self.assertEqual(paired_brier_uncertainty(self.rows[:100])["status"], "HOLD")

    def test_bad_baseline_holds(self):
        rows = [*self.rows]
        rows[-1] = {**rows[-1], "baseline_probability": float("nan")}
        self.assertEqual(paired_brier_uncertainty(rows)["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
