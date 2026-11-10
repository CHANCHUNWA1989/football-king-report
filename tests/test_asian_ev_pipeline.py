import unittest
from datetime import datetime, timedelta, timezone
from ops.asian_ev_pipeline import evaluate_research_quote

NOW = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
KICKOFF = NOW + timedelta(hours=1)


class PipelineTests(unittest.TestCase):
    def quote(self):
        return {"fixture_id": "fixture-1", "market_id": "asian-home",
                "source": "example-source", "source_quote_id": "quote-1",
                "observed_at_utc": NOW - timedelta(seconds=30), "decimal_odds": 2.0}

    def evaluate(self, quote=None, probabilities=None, line=-0.25):
        return evaluate_research_quote(
            self.quote() if quote is None else quote, now_utc=NOW, kickoff_utc=KICKOFF,
            probabilities={1: 0.6, -1: 0.4} if probabilities is None else probabilities, line=line)

    def test_valid_research_remains_nonproduction(self):
        r = self.evaluate()
        self.assertEqual(r["status"], "RESEARCH_ONLY")
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertEqual(len(r["quote_sha256"]), 64)
        self.assertIsInstance(r["research_ev"], float)

    def test_stale_quote_fails_closed(self):
        q = self.quote()
        q["observed_at_utc"] = NOW - timedelta(seconds=301)
        self.assertEqual(self.evaluate(q)["status"], "HOLD")

    def test_missing_provenance_fails_closed(self):
        q = self.quote()
        del q["source_quote_id"]
        self.assertEqual(self.evaluate(q)["status"], "HOLD")

    def test_invalid_probability_fails_closed(self):
        self.assertEqual(self.evaluate(probabilities={1: 0.9})["status"], "HOLD")

    def test_invalid_line_fails_closed(self):
        self.assertEqual(self.evaluate(line=float("nan"))["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
