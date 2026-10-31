"""Live market guard: synthetic fixtures only, never betting evidence."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_quote_snapshot_guard import audit_live_snapshot


def sample():
    return {
        "event_id": "fixture-123",
        "kickoff_utc": "2026-10-31T08:00:00Z",
        "decision_utc": "2026-10-31T08:30:00Z",
        "score": {"event_id": "fixture-123", "source": "official",
                  "upstream_updated_utc": "2026-10-31T08:29:50Z",
                  "captured_utc": "2026-10-31T08:29:55Z",
                  "home_goals": 0, "away_goals": 0},
        "stats": {"event_id": "fixture-123", "source": "stats",
                  "upstream_updated_utc": "2026-10-31T08:29:40Z",
                  "captured_utc": "2026-10-31T08:29:45Z",
                  "home_xg": 0.1, "away_xg": 0.3},
        "quote": {"event_id": "fixture-123", "source": "licensed-odds",
                  "upstream_updated_utc": "2026-10-31T08:29:45Z",
                  "captured_utc": "2026-10-31T08:29:50Z",
                  "market": "totals", "line": 2.25,
                  "decimal_price": 1.91, "bookmaker": "sample-book"}
    }


class LiveQuoteSnapshotGuardTests(unittest.TestCase):
    def test_fresh_same_event_is_research_only_not_ev(self):
        result = audit_live_snapshot(sample())
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertFalse(result["certified_positive_ev"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_stale_stats_with_fresh_capture_fails_closed(self):
        s = sample()
        s["stats"]["upstream_updated_utc"] = "2026-10-31T08:20:00Z"
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_cross_fixture_quote_fails_closed(self):
        s = sample()
        s["quote"]["event_id"] = "other-match"
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_after_decision_quote_fails_closed(self):
        s = sample()
        s["quote"]["upstream_updated_utc"] = "2026-10-31T08:31:00Z"
        s["quote"]["captured_utc"] = "2026-10-31T08:31:01Z"
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_missing_market_line_fails_closed(self):
        s = sample()
        del s["quote"]["line"]
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_booleans_are_not_valid_odds(self):
        s = sample()
        s["quote"]["decimal_price"] = True
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_naive_timestamp_fails_closed(self):
        s = sample()
        s["decision_utc"] = "2026-10-31T08:30:00"
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
