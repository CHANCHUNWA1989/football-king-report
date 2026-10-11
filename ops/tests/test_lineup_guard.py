"""Check lineup chronology without ever certifying official source authenticity."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lineup_guard import audit

FORECAST = {
    "league": "epl", "home": "Liverpool", "away": "Manchester City",
    "prediction_utc": "2026-10-11T22:45:00+08:00",
    "kickoff_utc": "2026-10-11T23:30:00+08:00",
}
EVIDENCE = {
    "fixture": {
        "league": "epl", "home": "Liverpool", "away": "Manchester City",
        "kickoff_utc": "2026-10-11T15:30:00Z"},
    "published_utc": "2026-10-11T22:32:00+08:00",
    "captured_utc": "2026-10-11T22:35:00+08:00",
    "home_starters": [f"home-player-{i}" for i in range(11)],
    "away_starters": [f"away-player-{i}" for i in range(11)],
    "source_url": "https://www.mancity.com/news",
}


class LineupGuardTests(unittest.TestCase):
    def setUp(self):
        self.f = {**FORECAST, "lineup_evidence": copy.deepcopy(EVIDENCE)}

    def test_missing_lineup_is_not_implicitly_verified(self):
        result = audit(FORECAST)
        self.assertEqual(result["status"], "MISSING")
        self.assertFalse(result["model_lineup_incorporation_verified"])

    def test_valid_lineup_chronology_is_still_unattested(self):
        result = audit(self.f)
        self.assertEqual(result["status"], "STRUCTURAL_RESEARCH_ONLY")
        self.assertTrue(result["lineup_usable_before_prediction"])
        self.assertFalse(result["official_lineup_authenticated"])
        self.assertFalse(result["eligible_for_betting"])
        self.assertNotIn("home_starters", result)
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_post_prediction_source_not_backfilled(self):
        self.f["lineup_evidence"]["published_utc"] = "2026-10-11T22:50:00+08:00"
        self.f["lineup_evidence"]["captured_utc"] = "2026-10-11T22:51:00+08:00"
        result = audit(self.f)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "LINEUP_AFTER_FORECAST_OR_INVALID_TIME")

    def test_mismatch_bad_xi_and_duplicate_prevent_silent_use(self):
        e = self.f["lineup_evidence"]
        e["fixture"]["away"] = "Arsenal"
        self.assertEqual(audit(self.f)["reason"], "LINEUP_FIXTURE_MISMATCH")
        e["fixture"]["away"] = "Manchester City"
        e["home_starters"][1] = e["home_starters"][0]
        self.assertEqual(audit(self.f)["reason"], "INVALID_STARTING_XI")
        e["home_starters"][1] = "home-player-1"
        e["away_starters"][1] = e["home_starters"][1]
        self.assertEqual(audit(self.f)["reason"], "CROSS_TEAM_DUPLICATE_PLAYER")

    def test_non_https_future_and_stale_decline(self):
        e = self.f["lineup_evidence"]
        e["source_url"] = "http://untrusted.example/xi"
        self.assertEqual(audit(self.f)["reason"], "INVALID_SOURCE_URL")
        e["source_url"] = "https://example.org/"
        e["published_utc"] = "2026-10-11T19:00:00+08:00"
        self.assertEqual(audit(self.f)["reason"], "LINEUP_TOO_EARLY_TO_ATTEST")
        e["published_utc"] = "2026-10-11T22:32:00+08:00"
        e["captured_utc"] = "2026-10-11T22:50:00+08:00"
        self.assertEqual(audit(self.f)["reason"], "LINEUP_AFTER_FORECAST_OR_INVALID_TIME")


if __name__ == "__main__":
    unittest.main()
