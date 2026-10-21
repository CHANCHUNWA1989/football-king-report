"""Tests for research-only bookmaker quote change comparison."""
import unittest
from ops.quote_snapshot_compare import compare_quotes

def quote(**changes):
    q = dict(provider="sample", bookmaker="book-a", fixture_id="fixture-1",
             provider_quote_id="q1", market="ASIAN_HANDICAP",
             selection="HOME", line=-0.25, decimal_odds=1.9,
             quote_utc="2026-10-21T10:00:00Z")
    q.update(changes)
    return q

def compare(a, b):
    return compare_quotes(a, b, previous_captured_utc="2026-10-21T10:01:00Z",
                          current_captured_utc="2026-10-21T10:06:00Z")

class QuoteComparisonTests(unittest.TestCase):
    def test_same_line_price_change(self):
        r = compare(quote(), quote(provider_quote_id="q2",
                     quote_utc="2026-10-21T10:05:00Z", decimal_odds=1.96))
        self.assertAlmostEqual(r["odds_delta_same_line"], 0.06)
        self.assertTrue(r["material_change_observed"])
        self.assertFalse(r["calibrated_positive_ev"])

    def test_line_change_no_price_delta(self):
        r = compare(quote(), quote(provider_quote_id="q2",
                     quote_utc="2026-10-21T10:05:00Z", line=-0.5))
        self.assertTrue(r["line_changed"])
        self.assertIsNone(r["odds_delta_same_line"])

    def test_unchanged(self):
        r = compare(quote(), quote(provider_quote_id="q2",
                     quote_utc="2026-10-21T10:05:00Z"))
        self.assertFalse(r["material_change_observed"])

    def test_cross_bookmaker_rejected(self):
        with self.assertRaises(ValueError):
            compare(quote(), quote(bookmaker="book-b", provider_quote_id="q2",
                                  quote_utc="2026-10-21T10:05:00Z"))

    def test_stale_provider_time_rejected(self):
        with self.assertRaises(ValueError):
            compare(quote(), quote(provider_quote_id="q2"))

    def test_reused_id_rejected(self):
        with self.assertRaises(ValueError):
            compare(quote(), quote(quote_utc="2026-10-21T10:05:00Z"))

    def test_different_market_rejected(self):
        with self.assertRaises(ValueError):
            compare(quote(), quote(provider_quote_id="q2", market="TOTALS",
                                  selection="OVER", line=2.5,
                                  quote_utc="2026-10-21T10:05:00Z"))

if __name__ == "__main__":
    unittest.main()
