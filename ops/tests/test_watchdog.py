"""Regression tests for independent published-site monitor."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from watchdog import evaluate, evaluate_research_layers


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

    def test_research_layers_require_hold_for_market_evidence(self):
        self.assertFalse(evaluate_research_layers(
            {"status": "INCONCLUSIVE", "all_leagues_verified": False,
             "production_recommendations": "DISABLED"},
            {"model_calibrated": False, "market_odds_available": False,
             "production_recommendations": "DISABLED", "predictions": [], "predictions_count": 0},
            {"status": "HOLD", "production_recommendations": "DISABLED"}))

    def test_improper_betting_status_fails_watchdog(self):
        errors = evaluate_research_layers(
            {"status": "PARTIAL_CHECK", "all_leagues_verified": False,
             "production_recommendations": "DISABLED"},
            {"model_calibrated": True, "market_odds_available": False,
             "production_recommendations": "DISABLED", "predictions": [], "predictions_count": 0},
            {"status": "HOLD", "production_recommendations": "DISABLED"})
        self.assertIn("INVALID_SHADOW_RESEARCH_PROVENANCE", errors)

    def test_shadow_count_mismatch_alerts(self):
        errors = evaluate_research_layers(
            {"status": "INCONCLUSIVE", "all_leagues_verified": False,
             "production_recommendations": "DISABLED"},
            {"model_calibrated": False, "market_odds_available": False,
             "production_recommendations": "DISABLED", "predictions": [], "predictions_count": 8},
            {"status": "HOLD", "production_recommendations": "DISABLED"})
        self.assertIn("SHADOW_COUNT_MISMATCH", errors)


if __name__ == "__main__":
    unittest.main()
