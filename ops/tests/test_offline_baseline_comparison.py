"""Synthetic paired baseline comparison regression tests."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_baseline_comparison import compare_heldout_baseline


class TestBaselineComparison(unittest.TestCase):
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
                "probability": 0.8, "baseline_probability": 0.5,
                "outcome": 1,
            })

    def test_better_model_on_synthetic_sample(self):
        result = compare_heldout_baseline(self.rows)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["test_count"], 40)
        self.assertEqual(result["model_brier"], 0.04)
        self.assertEqual(result["baseline_brier"], 0.25)
        self.assertEqual(result["brier_delta"], -0.21)
        self.assertTrue(result["model_better_on_sample"])
        self.assertFalse(result["model_validated"])

    def test_invalid_baseline_holds(self):
        rows = [*self.rows]
        rows[-1] = {**rows[-1], "baseline_probability": float("nan")}
        self.assertEqual(compare_heldout_baseline(rows)["status"], "HOLD")

    def test_missing_baseline_holds(self):
        rows = [*self.rows]
        rows[-1] = {key: value for key, value in rows[-1].items()
                    if key != "baseline_probability"}
        self.assertEqual(compare_heldout_baseline(rows)["status"], "HOLD")

    def test_insufficient_heldout_holds(self):
        self.assertEqual(compare_heldout_baseline(self.rows[:100])["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
