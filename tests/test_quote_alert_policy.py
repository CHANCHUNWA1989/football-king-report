"""Fail-closed tests for material odds change alerts."""
import unittest
from ops.quote_alert_policy import evaluate_quote_alert

def quote(**changes):
    q = dict(provider="research-feed", bookmaker="book-a",
             fixture_id="f1", provider_quote_id="q1",
             market="ASIAN_HANDICAP", selection="HOME",
             line=-0.25, decimal_odds=1.90,
             quote_utc="2026-10-21T10:00:00Z")
    q.update(changes)
    return q

def check(old, new, **kwargs):
    return evaluate_quote_alert(
        old, new, previous_captured_utc="2026-10-21T10:01:00Z",
        current_captured_utc="2026-10-21T10:06:00Z", **kwargs)

class QuoteAlertPolicyTests(unittest.TestCase):
    def test_minor_move_suppressed(self):
        result = check(quote(), quote(provider_quote_id="q2",
            quote_utc="2026-10-21T10:05:00Z", decimal_odds=1.92))
        self.assertFalse(result["notify"])
        self.assertEqual(result["reason"], "NO_MATERIAL_CHANGE")

    def test_major_move_alerts(self):
        result = check(quote(), quote(provider_quote_id="q2",
            quote_utc="2026-10-21T10:05:00Z", decimal_odds=2.00))
        self.assertTrue(result["notify"])
        self.assertEqual(result["reason"], "MATERIAL_ODDS_CHANGE")
        self.assertFalse(result["calibrated_positive_ev"])

    def test_line_change_alerts_without_false_odds_delta(self):
        result = check(quote(), quote(provider_quote_id="q2",
            quote_utc="2026-10-21T10:05:00Z", line=-0.5))
        self.assertEqual(result["reason"], "MARKET_LINE_CHANGED")
        self.assertIsNone(result["odds_delta_same_line"])

    def test_no_change_suppressed(self):
        self.assertFalse(check(quote(), quote(provider_quote_id="q2",
            quote_utc="2026-10-21T10:05:00Z"))["notify"])

    def test_threshold_invalid(self):
        for threshold in (0, -1, True, float("nan")):
            with self.subTest(threshold=threshold):
                with self.assertRaises(ValueError):
                    check(quote(), quote(provider_quote_id="q2",
                        quote_utc="2026-10-21T10:05:00Z"),
                        minimum_odds_change=threshold)

    def test_stale_snapshot_rejected(self):
        with self.assertRaises(ValueError):
            check(quote(), quote(provider_quote_id="q2"))

    def test_cross_bookmaker_rejected(self):
        with self.assertRaises(ValueError):
            check(quote(), quote(provider_quote_id="q2",
                bookmaker="book-b", quote_utc="2026-10-21T10:05:00Z"))

    def test_production_disabled(self):
        result = check(quote(), quote(provider_quote_id="q2",
            quote_utc="2026-10-21T10:05:00Z", decimal_odds=2.0))
        self.assertEqual(result["production_recommendations"], "DISABLED")

if __name__ == "__main__":
    unittest.main()
