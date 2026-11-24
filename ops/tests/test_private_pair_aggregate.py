import unittest
from datetime import datetime, timezone
from ops.private_pair_aggregate import aggregate, OUTPUT_SCHEMA


class AggregateTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 8, tzinfo=timezone.utc)
        self.feed = {"schema": "football-king-bound-h2h-feed-v1",
                     "production_recommendations": "DISABLED", "quotes": []}

    def test_no_forecasts_never_invented(self):
        r = aggregate(self.feed, now=self.now)
        self.assertEqual(r["reason"], "NO_INDEPENDENT_FORECAST_INPUT")
        self.assertEqual(r["validated_private_quote_count"], 0)
        self.assertFalse(r["positive_ev_verified"])

    def test_empty_forecasts_hold(self):
        self.assertEqual(aggregate(self.feed, [], now=self.now)["reason"],
                         "NO_INDEPENDENT_FORECAST_INPUT")

    def test_invalid_feed_holds(self):
        self.assertEqual(aggregate({}, now=self.now)["reason"], "INVALID_PRIVATE_FEED")

    def test_bad_quotes_holds(self):
        self.feed["quotes"] = "not-quotes"
        self.assertEqual(aggregate(self.feed, now=self.now)["reason"], "INVALID_PRIVATE_QUOTES")

    def test_no_details_exported(self):
        r = aggregate(self.feed, now=self.now)
        self.assertEqual(r["schema"], OUTPUT_SCHEMA)
        self.assertFalse(r["raw_odds_exported"])
        self.assertFalse(r["candidate_details_exported"])
        self.assertNotIn("unverified_research_candidates", r)


if __name__ == "__main__":
    unittest.main()
