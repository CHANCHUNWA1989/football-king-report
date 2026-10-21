"""Offline provider export to daily report integration tests."""
import unittest
from ops.offline_provider_export import adapt_export
from ops.daily_research_report import build_daily_research_report

NOW = "2026-10-21T10:00:00Z"
def fixture(quotes=None):
    return {"id":"f1","home":"Home","away":"Away",
            "kickoff_utc":"2026-10-21T12:00:00Z",
            "quotes":quotes if quotes is not None else []}
def quote(qid, at, odds=1.9):
    return {"id":qid,"bookmaker":"Book","market":"TOTALS",
            "selection":"OVER","line":2.5,"decimal_odds":odds,"quote_utc":at}
def adapt(fixtures, source="manual-export"):
    return adapt_export({"source":source,"fixtures":fixtures},generated_utc=NOW)

class OfflineExportTests(unittest.TestCase):
    def test_latest_prematch_quote_flows_into_report(self):
        inp = adapt([fixture([quote("old","2026-10-21T09:00:00Z"),
                              quote("new","2026-10-21T09:55:00Z")])])
        result = build_daily_research_report(inp["rows"],generated_utc=inp["generated_utc"])
        self.assertEqual(result["cards"][0]["quote"]["provider_quote_id"],"new")
        self.assertEqual(result["cards"][0]["status"],"RESEARCH_ONLY")
        self.assertFalse(result["positive_ev_verified"])

    def test_future_quote_never_used(self):
        inp = adapt([fixture([quote("future","2026-10-21T10:01:00Z")])])
        self.assertIsNone(inp["rows"][0]["quote"])

    def test_missing_quotes_no_recommendation(self):
        inp = adapt([fixture()])
        result = build_daily_research_report(inp["rows"],generated_utc=inp["generated_utc"])
        self.assertEqual(result["cards"][0]["status"],"NO_RECOMMENDATION")

    def test_missing_source_rejected(self):
        with self.assertRaises(ValueError):
            adapt([fixture()],source="")

    def test_invalid_quotes_rejected(self):
        with self.assertRaises(ValueError):
            adapt([fixture(quotes={})])

    def test_no_fabricated_probability(self):
        inp = adapt([fixture([quote("q","2026-10-21T09:55:00Z")])])
        self.assertNotIn("model_probability",inp["rows"][0])
        self.assertEqual(inp["production_recommendations"],"HOLD")

if __name__=="__main__":
    unittest.main()
