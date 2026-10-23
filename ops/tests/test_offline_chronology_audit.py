"""Synthetic chronology guard regression tests."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_chronology_audit import evaluate_chronological_history


class TestOfflineChronologyAudit(unittest.TestCase):
    def setUp(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.rows = []
        for i in range(30):
            start = base + timedelta(days=i)
            self.rows.append({
                "event_id": f"event-{i}", "probability": 0.6,
                "outcome": i % 2,
                "predicted_at_utc": (start - timedelta(hours=2)).isoformat(),
                "kickoff_at_utc": start.isoformat(),
                "settled_at_utc": (start + timedelta(hours=3)).isoformat(),
            })

    def test_valid_order_research_only(self):
        result = evaluate_chronological_history(self.rows)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertTrue(result["timestamp_order_checked"])
        self.assertFalse(result["source_authenticity_verified"])

    def test_prediction_after_kickoff_holds(self):
        rows = [*self.rows]
        rows[0] = {**rows[0], "predicted_at_utc": rows[0]["settled_at_utc"]}
        self.assertEqual(evaluate_chronological_history(rows)["status"], "HOLD")

    def test_settlement_before_kickoff_holds(self):
        rows = [*self.rows]
        rows[0] = {**rows[0], "settled_at_utc": rows[0]["predicted_at_utc"]}
        self.assertEqual(evaluate_chronological_history(rows)["status"], "HOLD")

    def test_out_of_order_rows_hold(self):
        rows = [self.rows[1], self.rows[0], *self.rows[2:]]
        self.assertEqual(evaluate_chronological_history(rows)["status"], "HOLD")

    def test_missing_or_naive_timestamp_holds(self):
        for value in (None, "2026-01-01T10:00:00", "not-a-date"):
            with self.subTest(value=value):
                rows = [*self.rows]
                rows[0] = {**rows[0], "predicted_at_utc": value}
                self.assertEqual(evaluate_chronological_history(rows)["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
