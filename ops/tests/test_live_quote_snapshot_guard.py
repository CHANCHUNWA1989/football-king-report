"""Synthetic-only tests for the fail-closed live evidence cut."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_quote_snapshot_guard import audit_live_snapshot


def sample():
    return {
        "event_id": "synthetic-fixture-123",
        "kickoff_utc": "2026-10-31T08:00:00Z",
        "decision_utc": "2026-10-31T08:30:00Z",
        "score": {
            "event_id": "synthetic-fixture-123", "source": "sample-official",
            "upstream_updated_utc": "2026-10-31T08:29:50Z",
            "captured_utc": "2026-10-31T08:29:55Z",
            "home_goals": 0, "away_goals": 0,
        },
        "stats": {
            "event_id": "synthetic-fixture-123", "source": "sample-stats",
            "upstream_updated_utc": "2026-10-31T08:29:53Z",
            "captured_utc": "2026-10-31T08:29:56Z",
            "home_xg": 0.1, "away_xg": 0.3,
        },
        "quote": {
            "event_id": "synthetic-fixture-123", "source": "sample-licensed-odds",
            "upstream_updated_utc": "2026-10-31T08:29:56Z",
            "captured_utc": "2026-10-31T08:29:58Z",
            "market": "totals", "selection": "over", "in_play": True,
            "line": 2.25, "decimal_price": 1.91, "bookmaker": "sample-book",
        },
    }


class LiveQuoteSnapshotGuardTests(unittest.TestCase):
    def test_fresh_input_is_research_only_not_positive_ev(self):
        output = audit_live_snapshot(sample())
        self.assertEqual(output["status"], "RESEARCH_ONLY")
        self.assertFalse(output["certified_positive_ev"])
        self.assertFalse(output["market_executable_verified"])
        self.assertFalse(output["probability_calibrated"])
        self.assertEqual(output["production_recommendations"], "DISABLED")

    def test_stale_upstream_rejected_despite_recent_capture(self):
        s = sample()
        s["stats"]["upstream_updated_utc"] = "2026-10-31T08:20:00Z"
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_score_updated_after_stats_rejected(self):
        s = sample()
        s["stats"]["upstream_updated_utc"] = "2026-10-31T08:29:49Z"
        self.assertIn("STATS_BEFORE_SCORE", audit_live_snapshot(s)["reasons"])

    def test_quote_before_goal_score_rejected(self):
        s = sample()
        s["score"]["home_goals"] = 1
        s["quote"]["upstream_updated_utc"] = "2026-10-31T08:29:51Z"
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_other_match_quote_rejected(self):
        s = sample()
        s["quote"]["event_id"] = "another-event"
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_future_quote_rejected(self):
        s = sample()
        s["quote"]["upstream_updated_utc"] = "2026-10-31T08:31:00Z"
        s["quote"]["captured_utc"] = "2026-10-31T08:31:01Z"
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_missing_line_rejected(self):
        s = sample()
        del s["quote"]["line"]
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_boolean_odds_rejected(self):
        s = sample()
        s["quote"]["decimal_price"] = True
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_naive_timestamp_rejected(self):
        s = sample()
        s["decision_utc"] = "2026-10-31T08:30:00"
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_unsupported_selection_rejected(self):
        s = sample()
        s["quote"]["selection"] = "away"
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_pre_match_quote_rejected(self):
        s = sample()
        s["quote"]["in_play"] = False
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_invalid_quarter_line_rejected(self):
        s = sample()
        s["quote"]["line"] = 2.30
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_invalid_xg_rejected(self):
        s = sample()
        s["stats"]["away_xg"] = float("nan")
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_invalid_age_limit_rejected(self):
        self.assertEqual(audit_live_snapshot(sample(), max_age_seconds=float("inf"))["status"], "HOLD")

    def test_asian_handicap_side_supported_but_not_ev(self):
        s = sample()
        s["quote"]["market"] = "asian_handicap"
        s["quote"]["selection"] = "away"
        s["quote"]["line"] = 0.75
        output = audit_live_snapshot(s)
        self.assertEqual(output["status"], "RESEARCH_ONLY")
        self.assertFalse(output["certified_positive_ev"])


if __name__ == "__main__":
    unittest.main()
