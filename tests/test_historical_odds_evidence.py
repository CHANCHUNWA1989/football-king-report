"""Regression tests for historical executable-price evidence gate."""
import unittest
from ops.historical_odds_evidence import validate_historical_price

def sample():
    return dict(fixture_id="f1", provider="licensed-source",
                market="total", selection="over", provider_quote_id="q1",
                evidence_uri="https://example.org/record/q1",
                settlement_basis="FULL_MATCH", decimal_odds=1.95,
                price_was_executable=True, market_phase="PREMATCH",
                quote_utc="2026-10-20T16:00:00Z",
                decision_utc="2026-10-20T16:01:00Z",
                kickoff_utc="2026-10-20T17:00:00Z")

class HistoricalEvidenceTests(unittest.TestCase):
    def test_complete_evidence_still_not_certified(self):
        r = validate_historical_price(sample())
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertEqual(r["status"], "EVIDENCE_PRESENT_NOT_INDEPENDENTLY_VERIFIED")

    def test_missing_evidence(self):
        q = sample()
        q["evidence_uri"] = ""
        with self.assertRaises(ValueError):
            validate_historical_price(q)

    def test_non_executable(self):
        q = sample()
        q["price_was_executable"] = False
        with self.assertRaises(ValueError):
            validate_historical_price(q)

    def test_prematch_leak(self):
        q = sample()
        q["decision_utc"] = "2026-10-20T17:01:00Z"
        with self.assertRaises(ValueError):
            validate_historical_price(q)

    def test_bad_price(self):
        q = sample()
        q["decimal_odds"] = 1
        with self.assertRaises(ValueError):
            validate_historical_price(q)

    def test_inplay_before_kickoff_rejected(self):
        q = sample()
        q.update(market_phase="INPLAY", match_minute=10,
                 home_goals=0, away_goals=0)
        with self.assertRaises(ValueError):
            validate_historical_price(q)

    def test_inplay_requires_state(self):
        q = sample()
        q.update(market_phase="INPLAY",
                 quote_utc="2026-10-20T17:10:00Z",
                 decision_utc="2026-10-20T17:11:00Z")
        with self.assertRaises(ValueError):
            validate_historical_price(q)

    def test_valid_inplay_still_not_certified(self):
        q = sample()
        q.update(market_phase="INPLAY",
                 quote_utc="2026-10-20T17:10:00Z",
                 decision_utc="2026-10-20T17:11:00Z",
                 match_minute=10, home_goals=0, away_goals=1)
        r = validate_historical_price(q)
        self.assertEqual(r["status"], "EVIDENCE_PRESENT_NOT_INDEPENDENTLY_VERIFIED")

    def test_reject_untrusted_uri_scheme(self):
        q = sample()
        q["evidence_uri"] = "http://example.org/record/q1"
        with self.assertRaises(ValueError):
            validate_historical_price(q)

if __name__ == "__main__":
    unittest.main()
