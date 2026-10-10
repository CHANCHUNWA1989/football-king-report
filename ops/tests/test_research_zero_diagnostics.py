"""Regression tests for no-pick diagnostics and fallback safety."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_recommender import build


class ZeroSelectionDiagnosticsTests(unittest.TestCase):
    def test_no_pairs_explains_missing_recommendations(self):
        now = datetime(2026, 10, 10, 0, 0, tzinfo=timezone.utc)
        shadow = {"status": "SHADOW_ONLY", "production_recommendations": "DISABLED",
                  "as_of_utc": now.isoformat(), "predictions": []}
        pairing = {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
                   "comparisons": []}
        status = {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED"}
        result = build(shadow, pairing, status, now=now)
        self.assertEqual(result["selected_count"], 0)
        self.assertEqual(result["fallback_reason"], "NO_STRICT_MARKET_MATCHES")
        self.assertEqual(result["diagnostics"]["paired_total"], 0)
        self.assertIsNotNone(result["diagnostics"]["no_output_explanation"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_stale_model_explains_hold(self):
        from datetime import timedelta
        now = datetime(2026, 10, 10, 0, 0, tzinfo=timezone.utc)
        shadow = {"status": "SHADOW_ONLY", "production_recommendations": "DISABLED",
                  "as_of_utc": (now - timedelta(hours=11)).isoformat()}
        pairing = {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
                   "comparisons": []}
        status = {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED"}
        result = build(shadow, pairing, status, now=now)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["diagnostics"]["no_output_explanation"], "STALE_MODEL_SNAPSHOT")

    def test_unsupported_league_is_separately_diagnosed(self):
        from datetime import timedelta
        now = datetime(2026, 10, 10, 0, 0, tzinfo=timezone.utc)
        captured = (now - timedelta(minutes=2)).isoformat()
        shadow = {"status": "SHADOW_ONLY", "production_recommendations": "DISABLED",
                  "as_of_utc": captured, "predictions": []}
        pair = {"case_id": "jleague-1", "league": "j1",
                "production_recommendations": "DISABLED", "available_for_betting": False}
        pairing = {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
                   "comparisons": [pair]}
        status = {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED"}
        result = build(shadow, pairing, status, now=now)
        self.assertEqual(result["excluded_reasons"]["UNSUPPORTED_LEAGUE"], 1)
        self.assertEqual(result["diagnostics"]["invalid_or_expired_pairs"], 1)

    def test_missing_kickoff_timestamp_has_specific_reason(self):
        from datetime import timedelta
        now = datetime(2026, 10, 10, 0, 0, tzinfo=timezone.utc)
        captured = (now - timedelta(minutes=2)).isoformat()
        shadow = {"status": "SHADOW_ONLY", "production_recommendations": "DISABLED",
                  "as_of_utc": captured, "predictions": []}
        pair = {"case_id": "missing-kickoff", "league": "bundesliga",
                "home": "Bayern", "away": "Dortmund", "model": [.65, .2, .15],
                "market": [.6, .25, .15], "prediction_utc": captured,
                "market_snapshot_utc": (now-timedelta(minutes=10)).isoformat(),
                "market_updated_utc": (now-timedelta(minutes=15)).isoformat(),
                "production_recommendations": "DISABLED", "available_for_betting": False}
        pairing = {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
                   "comparisons": [pair]}
        status = {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED"}
        result = build(shadow, pairing, status, now=now)
        self.assertEqual(result["excluded_reasons"]["MISSING_KICKOFF_UTC"], 1)


if __name__ == "__main__":
    unittest.main()
