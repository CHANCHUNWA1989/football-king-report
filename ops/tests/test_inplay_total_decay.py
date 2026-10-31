"""Offline synthetic regression tests; no live odds or betting claims."""
import unittest
from ops.inplay_total_decay import analyze


def example():
    return {
        "fixture_id": "synthetic-match-1", "bookmaker_id": "synthetic-book-1",
        "market": "full_time_total_goals", "source_kind": "MANUALLY_TRANSCRIBED",
        "kickoff_utc": "2026-10-31T08:40:00Z",
        "checked_at_utc": "2026-10-31T09:05:00Z",
        "opening": {"line": 3.0, "quoted_at_utc": "2026-10-31T08:30:00Z",
                    "goals_scored": 0},
        "current": {"line": 2.25, "quoted_at_utc": "2026-10-31T09:04:00Z",
                    "match_minute": 24, "goals_scored": 0},
    }


class InPlayTotalDecayTests(unittest.TestCase):
    def test_ordinary_clock_decay_is_not_smart_money(self):
        out = analyze(example())
        self.assertEqual(out["status"], "RESEARCH_ONLY")
        self.assertEqual(out["raw_line_change"], -0.75)
        self.assertEqual(out["time_only_line_reference"], 2.2)
        self.assertEqual(out["line_minus_reference"], 0.05)
        self.assertEqual(out["diagnostic"], "CLOCK_ONLY_REFERENCE_CLOSE")
        self.assertFalse(out["market_signal_verified"])
        self.assertFalse(out["positive_ev_verified"])
        self.assertEqual(out["production_recommendations"], "DISABLED")

    def test_existing_goal_updates_reference_but_not_probability(self):
        data = example()
        data["current"].update(goals_scored=1, line=3.25)
        out = analyze(data)
        self.assertEqual(out["status"], "RESEARCH_ONLY")
        self.assertEqual(out["time_only_line_reference"], 3.2)
        self.assertFalse(out["time_only_reference_is_predictive"])

    def test_other_bookmaker_is_hold(self):
        data = example()
        data["current"]["bookmaker_id"] = "other-book"
        out = analyze(data)
        self.assertEqual(out["status"], "HOLD")
        self.assertIn("MISMATCHED_QUOTE_IDENTITY", out["reasons"])

    def test_stale_and_future_quotes_hold(self):
        for stamp in ("2026-10-31T08:55:00Z", "2026-10-31T09:06:00Z"):
            data = example()
            data["current"]["quoted_at_utc"] = stamp
            self.assertEqual(analyze(data)["status"], "HOLD")

    def test_invalid_clock_and_goals_hold(self):
        for key, value in (("match_minute", True), ("match_minute", 91),
                           ("goals_scored", -1), ("goals_scored", 0.5)):
            with self.subTest(key=key, value=value):
                data = example()
                data["current"][key] = value
                self.assertEqual(analyze(data)["status"], "HOLD")

    def test_invalid_line_and_timestamp_hold(self):
        for value in (float("nan"), 2.3, True):
            data = example()
            data["current"]["line"] = value
            self.assertEqual(analyze(data)["status"], "HOLD")
        data = example()
        data["checked_at_utc"] = "2026-10-31T09:05:00"
        self.assertEqual(analyze(data)["status"], "HOLD")

    def test_unpaired_quote_holds(self):
        self.assertEqual(analyze(None)["status"], "HOLD")
        data = example()
        del data["opening"]
        self.assertEqual(analyze(data)["status"], "HOLD")

    def test_large_residual_requires_review_not_ev(self):
        data = example()
        data["current"]["line"] = 1.50
        out = analyze(data)
        self.assertEqual(out["diagnostic"], "REQUIRES_INDEPENDENT_REVIEW")
        self.assertFalse(out["market_signal_verified"])
        self.assertFalse(out["positive_ev_verified"])

    def test_opening_after_kickoff_holds(self):
        data = example()
        data["opening"]["quoted_at_utc"] = "2026-10-31T08:41:00Z"
        self.assertEqual(analyze(data)["status"], "HOLD")

    def test_impossible_match_clock_holds(self):
        data = example()
        data["current"]["match_minute"] = 60
        self.assertEqual(analyze(data)["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
