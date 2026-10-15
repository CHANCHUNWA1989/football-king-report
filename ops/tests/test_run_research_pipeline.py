import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_research_pipeline import run


class IntegratedResearchTests(unittest.TestCase):
    def test_empty_inputs_fail_closed(self):
        report, html = run([], [])
        self.assertEqual(report["accepted"], 0)
        self.assertEqual(report["status"], "HOLD")
        self.assertIn("正式推薦：未開放", html)
        self.assertEqual(report["input_audit"]["error_count"], 2)

    def test_invalid_batch_suppresses_valid_row_performance(self):
        good_forecast = {"event_id": "good", "forecast_utc": "2020-01-01T09:00:00Z",
                         "kickoff_utc": "2020-01-01T12:00:00Z",
                         "p_home": .5, "p_draw": .3, "p_away": .2}
        good_result = {"event_id": "good", "result": "H", "status": "FINAL",
                       "settled_utc": "2020-01-01T15:00:00Z",
                       "source": "provider", "independently_verified": True}
        bad_result = {"event_id": "bad", "result": "H", "status": "LIVE",
                      "settled_utc": "2020-01-01T15:00:00Z",
                      "source": "provider", "independently_verified": False}
        report, _ = run([good_forecast], [good_result, bad_result])
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["accepted_before_audit"], 1)
        self.assertEqual(report["accepted"], 0)
        self.assertIsNone(report["mean_brier"])
        self.assertIsNone(report["top_probability_accuracy"])

    def test_invalid_probability_suppresses_batch_metrics(self):
        forecast = {"event_id": "bad-prob", "forecast_utc": "2020-01-01T09:00:00Z",
                    "kickoff_utc": "2020-01-01T12:00:00Z",
                    "p_home": .9, "p_draw": .9, "p_away": .9}
        result = {"event_id": "bad-prob", "result": "H", "status": "FINAL",
                  "settled_utc": "2020-01-01T15:00:00Z",
                  "source": "provider", "independently_verified": True}
        report, _ = run([forecast], [result])
        self.assertEqual(report["input_audit"]["status"], "RESEARCH_ONLY")
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["accepted"], 0)
        self.assertIsNone(report["mean_brier"])

    def test_unmatched_forecast_suppresses_batch_metrics(self):
        forecast = {"event_id": "unmatched", "forecast_utc": "2020-01-01T09:00:00Z",
                    "kickoff_utc": "2020-01-01T12:00:00Z",
                    "p_home": .5, "p_draw": .3, "p_away": .2}
        report, _ = run([forecast], [])
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["unmatched_or_unverified"], 1)

    def test_unverified_results_never_promoted(self):
        forecast = [{"event_id": "x", "forecast_utc": "2026-10-14T10:00:00Z",
                     "kickoff_utc": "2026-10-14T12:00:00Z",
                     "p_home": .4, "p_draw": .3, "p_away": .3}]
        result = [{"event_id": "x", "result": "H", "status": "FINAL",
                   "settled_utc": "2026-10-14T15:00:00Z",
                   "source": "provider", "independently_verified": False}]
        report, html = run(forecast, result)
        self.assertEqual(report["accepted"], 0)
        self.assertEqual(report["input_audit"]["status"], "HOLD")
        self.assertEqual(report["status"], "HOLD")
        self.assertIn("正式推薦：未開放", html)


if __name__ == "__main__":
    unittest.main()
