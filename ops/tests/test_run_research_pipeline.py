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
        self.assertEqual(report["input_audit"]["error_count"], 0)

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
