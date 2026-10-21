"""Regression tests for free, provider-neutral research odds intake."""
import unittest
from ops.free_odds_intake import normalize_quote

def sample(**changes):
    raw = dict(provider="free-provider", fixture_id="fixture-1",
               provider_quote_id="quote-1", bookmaker="book-a",
               market="ASIAN_HANDICAP", selection="HOME",
               line=-0.25, decimal_odds=1.94,
               quote_utc="2026-10-21T10:00:00Z")
    raw.update(changes)
    return raw

class FreeOddsIntakeTests(unittest.TestCase):
    def intake(self, raw):
        return normalize_quote(raw, captured_utc="2026-10-21T10:01:00Z")

    def test_valid_quote_remains_unverified(self):
        result = self.intake(sample())
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["price_executable_verified"])
        self.assertFalse(result["calibrated_positive_ev"])

    def test_valid_totals(self):
        self.assertEqual(self.intake(sample(market="TOTALS", selection="OVER",
                                            line=2.75))["line"], 2.75)

    def test_missing_provider(self):
        with self.assertRaises(ValueError):
            self.intake(sample(provider=""))

    def test_bad_odds(self):
        with self.assertRaises(ValueError):
            self.intake(sample(decimal_odds=1))

    def test_bad_line(self):
        with self.assertRaises(ValueError):
            self.intake(sample(line=-0.3))

    def test_quote_in_future(self):
        with self.assertRaises(ValueError):
            self.intake(sample(quote_utc="2026-10-21T10:02:00Z"))

    def test_naive_time(self):
        with self.assertRaises(ValueError):
            self.intake(sample(quote_utc="2026-10-21T10:00:00"))

    def test_wrong_market_selection(self):
        with self.assertRaises(ValueError):
            self.intake(sample(market="TOTALS", selection="HOME"))

    def test_boolean_odds_rejected(self):
        with self.assertRaises(ValueError):
            self.intake(sample(decimal_odds=True))

if __name__ == "__main__":
    unittest.main()
