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

    def test_post_kickoff_forecast_is_rejected(self):
        forecast = {"event_id": "late", "forecast_utc": "2020-01-01T13:00:00Z",
                    "kickoff_utc": "2020-01-01T12:00:00Z"}
        report = inspect([forecast], [])
        self.assertIn("FORECAST_NOT_PREMATCH", [e["reason"] for e in report["errors"]])

    def test_final_outcome_requires_source_and_result(self):
        result = {"event_id": "r1", "settled_utc": "2020-01-01T15:00:00Z",
                  "status": "FINAL", "independently_verified": True}
        report = inspect([], [result])
        reasons = [e["reason"] for e in report["errors"]]
        self.assertIn("MISSING_RESULT_SOURCE", reasons)
        self.assertIn("INVALID_FINAL_OUTCOME", reasons)

    def test_bookmaker_consensus_cannot_be_passed_as_model_forecast(self):
        forecast = {"event_id": "mkt-1", "forecast_utc": "2020-01-01T10:00:00Z",
                    "kickoff_utc": "2020-01-01T12:00:00Z",
                    "probabilities_are_no_vig_consensus": True,
                    "prediction_or_value_bet": False}
        result = {"event_id": "mkt-1", "settled_utc": "2020-01-01T15:00:00Z",
                  "status": "FINAL", "independently_verified": True}
        report = inspect([forecast], [result])
        self.assertEqual(report["status"], "HOLD")
        self.assertIn("MARKET_CONSENSUS_NOT_MODEL_FORECAST",
                      [e["reason"] for e in report["errors"]])

    def test_future_forecast_rejected(self):
        report = inspect([{"event_id": "a", "forecast_utc": "2099-01-01T00:00:00Z",
                           "kickoff_utc": "2099-01-02T00:00:00Z"}], [])
        self.assertEqual(report["status"], "HOLD")
        self.assertIn("FUTURE_FORECAST_UTC", [e["reason"] for e in report["errors"]])


if __name__ == "__main__":
    unittest.main()
