import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_input_audit import inspect


class InputAuditTests(unittest.TestCase):
    def test_empty_data_is_not_a_production_approval(self):
        report = inspect([], [])
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertEqual(report["forecast_count"], 0)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["error_count"], 2)

    def test_unfinished_results_rejected(self):
        report = inspect([], [{"event_id": "a", "settled_utc": "2020-01-01T10:00:00Z",
                               "status": "LIVE", "independently_verified": False}])
        self.assertEqual(report["status"], "HOLD")
        self.assertIn("NOT_FINAL", [e["reason"] for e in report["errors"]])

    def test_duplicate_forecasts_are_rejected(self):
        row = {"event_id": "duplicate", "forecast_utc": "2020-01-01T10:00:00Z",
               "kickoff_utc": "2020-01-01T12:00:00Z"}
        report = inspect([row, dict(row)], [])
        self.assertEqual(report["status"], "HOLD")
        self.assertIn("DUPLICATE_EVENT_ID", [e["reason"] for e in report["errors"]])

    def test_duplicate_results_are_rejected(self):
        row = {"event_id": "duplicate", "settled_utc": "2020-01-01T15:00:00Z",
               "status": "FINAL", "independently_verified": True}
        report = inspect([], [row, dict(row)])
        self.assertEqual(report["status"], "HOLD")
        self.assertIn("DUPLICATE_EVENT_ID", [e["reason"] for e in report["errors"]])

    def test_future_forecast_rejected(self):
        report = inspect([{"event_id": "a", "forecast_utc": "2099-01-01T00:00:00Z",
                           "kickoff_utc": "2099-01-02T00:00:00Z"}], [])
        self.assertEqual(report["status"], "HOLD")
        self.assertIn("FUTURE_FORECAST_UTC", [e["reason"] for e in report["errors"]])


if __name__ == "__main__":
    unittest.main()
