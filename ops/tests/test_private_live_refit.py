import unittest
from datetime import datetime, timezone
from ops.private_live_refit import build


class PrivateLiveRefitTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
        self.feed = {"schema": "football-king-bound-h2h-feed-v1",
                     "production_recommendations": "DISABLED", "quotes": []}

    def test_missing_quotes_fails_closed(self):
        del self.feed["quotes"]
        r = build(self.feed, [], now=self.now)
        self.assertEqual(r["reason"], "INVALID_PRIVATE_QUOTES")

    def test_no_quotes_fails_closed(self):
        r = build(self.feed, [], now=self.now)
        self.assertEqual(r["reason"], "NO_CURRENT_VERIFIED_BOUND_QUOTES")
        self.assertEqual(r["forecasts"], [])

    def test_missing_history_fails_closed(self):
        self.assertEqual(build(self.feed, None, now=self.now)["reason"], "INVALID_INPUT")

    def test_no_consensus_fallback(self):
        self.feed["consensus_probabilities"] = {"H": .8, "D": .1, "A": .1}
        r = build(self.feed, [], now=self.now)
        self.assertEqual(r["forecasts"], [])

    def test_invalid_model_fails_closed(self):
        self.assertEqual(build(self.feed, [], now=self.now, model="magic")["reason"],
                         "INVALID_INPUT")

    def test_production_enabled_rejected(self):
        self.feed["production_recommendations"] = "ENABLED"
        self.assertEqual(build(self.feed, [], now=self.now)["reason"], "INVALID_INPUT")


if __name__ == "__main__":
    unittest.main()
