"""Pinned preflight synthetic regression tests."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_pinned_preflight import validate_pinned_forecast_rows


class TestPinnedPreflight(unittest.TestCase):
    def setUp(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.rows = []
        for i in range(90):
            kickoff = base + timedelta(days=i)
            self.rows.append({
                "event_id": f"match-{i}", "model_version": "v1",
                "predicted_at_utc": (kickoff - timedelta(hours=2)).isoformat(),
                "kickoff_at_utc": kickoff.isoformat(),
                "settled_at_utc": (kickoff + timedelta(hours=3)).isoformat(),
                "probability": 0.6, "outcome": 1,
            })

    def _status(self, rows):
        return validate_pinned_forecast_rows(
            rows, expected_model_version="v1")["status"]

    def test_valid_rows(self):
        self.assertEqual(self._status(self.rows), "RESEARCH_ONLY")

    def test_duplicate_event_holds(self):
        rows = [*self.rows]
        rows[-1] = {**rows[-1], "event_id": rows[0]["event_id"]}
        self.assertEqual(self._status(rows), "HOLD")

    def test_invalid_probability_holds(self):
        rows = [*self.rows]
        rows[-1] = {**rows[-1], "probability": float("nan")}
        self.assertEqual(self._status(rows), "HOLD")

    def test_nonbinary_outcome_holds(self):
        rows = [*self.rows]
        rows[-1] = {**rows[-1], "outcome": 2}
        self.assertEqual(self._status(rows), "HOLD")

    def test_mixed_model_holds(self):
        rows = [*self.rows]
        rows[-1] = {**rows[-1], "model_version": "v2"}
        self.assertEqual(self._status(rows), "HOLD")

    def test_post_kickoff_forecast_holds(self):
        rows = [*self.rows]
        rows[-1] = {**rows[-1], "predicted_at_utc": rows[-1]["settled_at_utc"]}
        self.assertEqual(self._status(rows), "HOLD")


if __name__ == "__main__":
    unittest.main()
