"""Daily research report tests: no fabricated odds or production betting."""
import unittest
from ops.daily_research_report import build_daily_research_report

NOW = "2026-10-21T10:00:00Z"

def item(**changes):
    row = dict(fixture_id="f1", home_team="Home", away_team="Away",
               kickoff_utc="2026-10-21T12:00:00Z",
               quote=dict(provider="source", fixture_id="f1",
                          provider_quote_id="q1", bookmaker="book",
                          market="TOTALS", selection="OVER", line=2.5,
                          decimal_odds=1.9, quote_utc="2026-10-21T09:55:00Z"))
    row.update(changes)
    return row

def build(rows):
    return build_daily_research_report(rows, generated_utc=NOW)

class DailyResearchReportTests(unittest.TestCase):
    def test_usable_quote_is_research_only(self):
        r = build([item()])
        self.assertEqual(r["cards"][0]["status"], "RESEARCH_ONLY")
        self.assertEqual(r["cards"][0]["betting_recommendation"], "HOLD")
        self.assertFalse(r["positive_ev_verified"])

    def test_missing_quote_no_recommendation(self):
        r = build([item(quote=None)])
        self.assertEqual(r["cards"][0]["reason"], "MISSING_QUOTE")
        self.assertIsNone(r["cards"][0]["quote"])

    def test_stale_quote_no_recommendation(self):
        q = item()["quote"].copy()
        q["quote_utc"] = "2026-10-21T08:00:00Z"
        self.assertEqual(build([item(quote=q)])["cards"][0]["reason"], "STALE_QUOTE")

    def test_started_match_no_recommendation(self):
        r = build([item(kickoff_utc="2026-10-21T09:00:00Z")])
        self.assertEqual(r["cards"][0]["reason"], "MATCH_STARTED_OR_FINISHED")

    def test_wrong_fixture_quote_rejected(self):
        q = item()["quote"].copy()
        q["fixture_id"] = "other"
        with self.assertRaises(ValueError):
            build([item(quote=q)])

    def test_duplicate_fixture_rejected(self):
        with self.assertRaises(ValueError):
            build([item(), item()])

    def test_uncalibrated_probability_never_verified(self):
        r = build([item(model_probability=0.6)])
        self.assertEqual(r["cards"][0]["model_probability_uncalibrated"], 0.6)
        self.assertEqual(r["cards"][0]["ev_status"], "UNVERIFIED_NOT_CALIBRATED")

    def test_invalid_probability_rejected(self):
        with self.assertRaises(ValueError):
            build([item(model_probability=1.2)])

    def test_empty_report_safe(self):
        r = build([])
        self.assertEqual(r["research_only_count"], 0)
        self.assertEqual(r["production_recommendations"], "HOLD")

if __name__ == "__main__":
    unittest.main()
