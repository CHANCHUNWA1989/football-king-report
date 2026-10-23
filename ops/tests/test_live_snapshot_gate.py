"""Offline tests for synchronized live snapshot safety gate."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_snapshot_gate import assess_snapshot


class TestLiveSnapshot(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 23, 10, tzinfo=timezone.utc)
        self.score = {"source_event_id": "fixture-1", "source_authorized": True,
                      "status": "LIVE", "minute": 47, "home_goals": 1,
                      "away_goals": 0, "source_last_update_utc": self.now.isoformat()}
        self.quote = {"source_event_id": "fixture-1", "bookmaker": "example",
                      "market": "totals", "selection": "over_2.5",
                      "market_last_update_utc": self.now.isoformat(),
                      "decimal_odds": 1.91, "source_authorized": True, "is_live": True}

    def check(self, score=None, quote=None):
        return assess_snapshot(self.score if score is None else score,
                               self.quote if quote is None else quote,
                               now=self.now)

    def test_valid_research_only(self):
        result = self.check()
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_mismatched_events_hold(self):
        self.assertEqual(self.check(quote={**self.quote, "source_event_id": "other"})["status"], "HOLD")

    def test_score_age_hold(self):
        old = (self.now - timedelta(seconds=91)).isoformat()
        self.assertEqual(self.check(score={**self.score, "source_last_update_utc": old})["status"], "HOLD")

    def test_not_live_hold(self):
        for status in ("FT", "HT", "SUSPENDED", None):
            with self.subTest(status=status):
                self.assertEqual(self.check(score={**self.score, "status": status})["status"], "HOLD")

    def test_invalid_scores_hold(self):
        for field, value in (("minute", True), ("home_goals", -1), ("away_goals", "2")):
            with self.subTest(field=field):
                self.assertEqual(self.check(score={**self.score, field: value})["status"], "HOLD")

    def test_stale_quote_hold(self):
        old = (self.now - timedelta(seconds=121)).isoformat()
        self.assertEqual(self.check(quote={**self.quote, "market_last_update_utc": old})["status"], "HOLD")

    def test_unverified_score_hold(self):
        self.assertEqual(self.check(score={**self.score, "source_authorized": False})["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
