"""Offline CLI integration tests; no live provider or betting account."""
import json
import tempfile
import unittest
from pathlib import Path
from ops.daily_research_cli import run

class DailyResearchCLITests(unittest.TestCase):
    def test_end_to_end_report_is_hold(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "input.json", Path(folder) / "out.json"
            source.write_text(json.dumps({
                "generated_utc": "2026-10-21T10:00:00Z",
                "rows": [{
                    "fixture_id": "f1", "home_team": "Home",
                    "away_team": "Away", "kickoff_utc": "2026-10-21T12:00:00Z",
                    "quote": {
                        "provider": "test-fixture", "fixture_id": "f1",
                        "provider_quote_id": "q1", "bookmaker": "test-book",
                        "market": "TOTALS", "selection": "OVER",
                        "line": 2.5, "decimal_odds": 1.9,
                        "quote_utc": "2026-10-21T09:55:00Z"
                    }
                }]
            }), encoding="utf-8")
            report = run(source, target)
            saved = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(report, saved)
            self.assertEqual(saved["cards"][0]["status"], "RESEARCH_ONLY")
            self.assertEqual(saved["production_recommendations"], "HOLD")
            self.assertFalse(saved["positive_ev_verified"])

    def test_missing_quote_is_no_recommendation(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "input.json", Path(folder) / "out.json"
            source.write_text(json.dumps({
                "generated_utc": "2026-10-21T10:00:00Z",
                "rows": [{
                    "fixture_id": "f1", "home_team": "Home",
                    "away_team": "Away", "kickoff_utc": "2026-10-21T12:00:00Z",
                    "quote": None
                }]
            }), encoding="utf-8")
            self.assertEqual(run(source, target)["cards"][0]["status"], "NO_RECOMMENDATION")

    def test_same_path_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.json"
            with self.assertRaises(ValueError):
                run(source, source)

    def test_bad_payload_no_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "input.json", Path(folder) / "out.json"
            source.write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError):
                run(source, target)
            self.assertFalse(target.exists())

if __name__ == "__main__":
    unittest.main()
