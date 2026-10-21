import unittest
from datetime import datetime, timedelta, timezone
from ops.asian_ev_quote_gate import assess_quote

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
KICKOFF = NOW + timedelta(hours=1)


class QuoteGateTests(unittest.TestCase):
    def quote(self):
        return {"fixture_id": "match-123", "market_id": "ah-home-minus-0.25",
                "source": "provider-A", "decimal_odds": 1.95,
                "observed_at_utc": NOW - timedelta(seconds=60)}

    def test_fresh_quote_is_research_only(self):
        decision = assess_quote(self.quote(), now_utc=NOW, kickoff_utc=KICKOFF)
        self.assertTrue(decision["eligible_for_research"])
        self.assertEqual(decision["production_recommendations"], "DISABLED")

    def test_stale_quote_rejected(self):
        q = self.quote()
        q["observed_at_utc"] = NOW - timedelta(seconds=301)
        self.assertIn("STALE_QUOTE", assess_quote(q, now_utc=NOW, kickoff_utc=KICKOFF)["reasons"])

    def test_future_quote_rejected(self):
        q = self.quote()
        q["observed_at_utc"] = NOW + timedelta(seconds=1)
        self.assertIn("FUTURE_QUOTE", assess_quote(q, now_utc=NOW, kickoff_utc=KICKOFF)["reasons"])

    def test_in_play_rejected(self):
        self.assertIn("MATCH_ALREADY_STARTED", assess_quote(self.quote(), now_utc=KICKOFF, kickoff_utc=KICKOFF)["reasons"])

    def test_invalid_odds_and_identity_rejected(self):
        q = self.quote()
        q["decimal_odds"] = True
        q["fixture_id"] = ""
        reasons = assess_quote(q, now_utc=NOW, kickoff_utc=KICKOFF)["reasons"]
        self.assertIn("INVALID_ODDS", reasons)
        self.assertIn("MISSING_FIXTURE_ID", reasons)

    def test_naive_timestamp_rejected(self):
        q = self.quote()
        q["observed_at_utc"] = NOW.replace(tzinfo=None)
        self.assertIn("INVALID_OBSERVED_TIME", assess_quote(q, now_utc=NOW, kickoff_utc=KICKOFF)["reasons"])


if __name__ == "__main__":
    unittest.main()
