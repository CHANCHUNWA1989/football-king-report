"""Tests for human-readable daily report fail-closed rendering."""
import unittest
from ops.daily_research_markdown import render_markdown
from ops.daily_research_report import build_daily_research_report

NOW = "2026-10-21T10:00:00Z"
def report(rows):
    return build_daily_research_report(rows, generated_utc=NOW)

class MarkdownReportTests(unittest.TestCase):
    def test_empty_report_never_invents_picks(self):
        body = render_markdown(report([]))
        self.assertIn("沒有賽事輸入", body)
        self.assertIn("HOLD", body)

    def test_quote_provenance_and_unverified_ev(self):
        rows = [{
            "fixture_id": "f1", "home_team": "Home", "away_team": "Away",
            "kickoff_utc": "2026-10-21T12:00:00Z",
            "quote": {
                "provider": "offline-test", "fixture_id": "f1",
                "provider_quote_id": "q1", "bookmaker": "test-book",
                "market": "TOTALS", "selection": "OVER", "line": 2.5,
                "decimal_odds": 1.9, "quote_utc": "2026-10-21T09:55:00Z"
            }
        }]
        body = render_markdown(report(rows))
        for text in ("offline-test", "q1", "1.9", "未經驗證", "HOLD"):
            self.assertIn(text, body)

    def test_missing_quote_is_explicit(self):
        rows = [{"fixture_id": "f1", "home_team": "Home",
                 "away_team": "Away", "kickoff_utc": "2026-10-21T12:00:00Z",
                 "quote": None}]
        body = render_markdown(report(rows))
        self.assertIn("無可用報價", body)
        self.assertIn("NO_RECOMMENDATION", body)

    def test_unsafe_report_rejected(self):
        r = report([])
        r["production_recommendations"] = "ENABLED"
        with self.assertRaises(ValueError):
            render_markdown(r)

    def test_unsafe_card_rejected(self):
        rows = [{"fixture_id": "f1", "home_team": "Home",
                 "away_team": "Away", "kickoff_utc": "2026-10-21T12:00:00Z",
                 "quote": None}]
        r = report(rows)
        r["cards"][0]["betting_recommendation"] = "BET"
        with self.assertRaises(ValueError):
            render_markdown(r)

if __name__ == "__main__":
    unittest.main()
