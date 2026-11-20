"""Synthetic offline split audit tests."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_temporal_split import split_historical_forecasts


class TestTemporalSplit(unittest.TestCase):
    def setUp(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.rows = []
        for i in range(60):
            kickoff = base + timedelta(days=i)
            self.rows.append({
                "event_id": f"match-{i}",
                "predicted_at_utc": (kickoff - timedelta(hours=2)).isoformat(),
                "kickoff_at_utc": kickoff.isoformat(),
                "settled_at_utc": (kickoff + timedelta(hours=3)).isoformat(),
            })

    def test_disjoint_train_and_test(self):
        result = split_historical_forecasts(self.rows)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["test_count"], 12)
        self.assertTrue(set(result["train_event_ids"]).isdisjoint(result["test_event_ids"]))
        self.assertFalse(result["model_validated"])

    def test_duplicate_event_holds(self):
        rows = [*self.rows]
        rows[1] = {**rows[1], "event_id": rows[0]["event_id"]}
        self.assertEqual(split_historical_forecasts(rows)["status"], "HOLD")

    def test_unsettled_training_near_test_excluded(self):
        rows = [*self.rows]
        rows[47] = {**rows[47], "settled_at_utc":
                    (datetime(2026, 2, 19, tzinfo=timezone.utc)).isoformat()}
        result = split_historical_forecasts(rows)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertGreaterEqual(result["excluded_train_count"], 1)

    def test_wrong_order_holds(self):
        rows = [self.rows[1], self.rows[0], *self.rows[2:]]
        self.assertEqual(split_historical_forecasts(rows)["status"], "HOLD")

    def test_insufficient_history_holds(self):
        self.assertEqual(split_historical_forecasts(self.rows[:40])["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
