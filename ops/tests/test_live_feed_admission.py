"""Offline admission integration tests; no API calls or secrets."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_feed_admission import admit_live_feed


class TestLiveFeedAdmission(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 23, 10, tzinfo=timezone.utc)
        ts = self.now.isoformat()
        self.score = {"source_event_id": "f1", "source_authorized": True,
                      "status": "LIVE", "minute": 51, "home_goals": 1,
                      "away_goals": 1, "source_last_update_utc": ts}
        self.quote = {"source_event_id": "f1", "bookmaker": "licensed-example",
                      "market": "totals", "selection": "over_2.5",
                      "market_last_update_utc": ts, "decimal_odds": 1.92,
                      "source_authorized": True, "is_live": True}

    def call(self, score=None, quote=None):
        return admit_live_feed({"score": self.score if score is None else score,
                                "quote": self.quote if quote is None else quote},
                               now=self.now)

    def test_valid_snapshot_stays_research_only(self):
        result = self.call()
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertEqual(len(result["observations"]), 1)
        self.assertFalse(result["observations"][0]["validated_positive_ev"])

    def test_invalid_event_never_leaks_observation(self):
        result = self.call(quote={**self.quote, "source_event_id": "f2"})
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["observations"], [])

    def test_stale_score_never_leaks_observation(self):
        old = (self.now - timedelta(seconds=100)).isoformat()
        result = self.call(score={**self.score, "source_last_update_utc": old})
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["observations"], [])

    def test_consensus_cannot_masquerade_as_bookmaker(self):
        result = self.call(quote={**self.quote, "probabilities_are_no_vig_consensus": True})
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["observations"], [])

    def test_bad_payload_is_hold(self):
        result = admit_live_feed(None, now=self.now)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["observations"], [])


if __name__ == "__main__":
    unittest.main()
