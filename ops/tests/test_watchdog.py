"""Regression tests for independent published-site monitor."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from watchdog import evaluate


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 9, 4, tzinfo=timezone.utc)
        self.checked = (self.now - timedelta(hours=2)).isoformat()
        self.state = {"checked_utc": self.checked, "status": "RESEARCH_ONLY",
                      "quality_status": "RESEARCH_ONLY",
                      "production_recommendations": "DISABLED"}
        self.quality = {"checked_utc": self.checked, "status": "RESEARCH_ONLY",
                        "critical_errors": []}

    def test_fresh_research_publication_ok(self):
        self.assertTrue(evaluate(self.state, self.quality, now=self.now)["ok"])

    def test_stale_publication_alerts(self):
        self.state["checked_utc"] = self.quality["checked_utc"] = (
            self.now - timedelta(hours=13)).isoformat()
        self.assertIn("PUBLISHED_REPORT_STALE_OR_FUTURE",
                      evaluate(self.state, self.quality, now=self.now)["failures"])

    def test_hold_reports_source_alert(self):
        self.state["status"] = "HOLD"
        self.state["quality_status"] = self.quality["status"] = "HOLD"
        self.assertIn("PUBLIC_SOURCE_HOLD",
                      evaluate(self.state, self.quality, now=self.now)["failures"])

    def test_recommendation_safety_alert(self):
        self.state["production_recommendations"] = "ENABLED"
        self.assertIn("UNSAFE_RECOMMENDATIONS_ENABLED",
                      evaluate(self.state, self.quality, now=self.now)["failures"])


if __name__ == "__main__":
    unittest.main()
