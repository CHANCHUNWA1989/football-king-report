import dataclasses
import json
import math
import unittest
from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

from ops.user_ev_policy import (
    MAX_QUOTE_AGE_SECONDS, MIN_EV, MIN_ODDS, evaluate_binary_market,
)


class EVPolicyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
        self.args = dict(
            odds=2.10, win_probability=.55, source="unattested_user_screenshot",
            quote_at=self.now-timedelta(minutes=2),
            kickoff_at=self.now+timedelta(hours=2),
            model_calibrated=True, model_validated=True,
            identity_verified=True, now=self.now,
        )

    def decision(self, **changes):
        return evaluate_binary_market(**dict(self.args, **changes))

    def assert_hold(self, reason=None, **changes):
        decision = self.decision(**changes)
        self.assertEqual(decision.status, "HOLD")
        if reason is not None:
            self.assertEqual(decision.reason, reason)
        json.dumps(dataclasses.asdict(decision), allow_nan=False)
        return decision

    def test_positive_is_conditional_unverified_arithmetic_only(self):
        decision = self.decision()
        self.assertEqual(decision.status, "UNVERIFIED_RESEARCH")
        self.assertEqual(decision.reason, "CONDITIONAL_EV_ARITHMETIC_ONLY")
        self.assertAlmostEqual(decision.ev, .155)
        self.assertAlmostEqual(decision.fair_odds, 1 / .55)
        self.assertEqual(set(dataclasses.asdict(decision)),
                         {"status", "reason", "ev", "fair_odds"})
        self.assertNotIn("ELIGIBLE", decision.status)
        json.dumps(dataclasses.asdict(decision), allow_nan=False)

    def test_caller_true_claims_and_source_text_never_authenticate_inputs(self):
        for source in ("unattested_user_screenshot", "https://example.test/quote", "reviewed"):
            with self.subTest(source=source):
                decision = self.decision(source=source)
                self.assertEqual((decision.status, decision.reason),
                                 ("UNVERIFIED_RESEARCH", "CONDITIONAL_EV_ARITHMETIC_ONLY"))

    def test_each_claim_requires_exact_boolean_true(self):
        invalid = (False, None, 0, 1, "false", "true", [], {}, object())
        for key in ("model_calibrated", "model_validated", "identity_verified"):
            for value in invalid:
                with self.subTest(key=key, value_type=type(value).__name__):
                    self.assert_hold(**{key: value})

    def test_minimum_odds_boundary_is_unchanged(self):
        self.assertEqual(MIN_ODDS, 1.80)
        self.assert_hold("ODDS_BELOW_MIN_OR_INVALID", odds=1.79)
        self.assertEqual(self.decision(odds=MIN_ODDS, win_probability=.6).status,
                         "UNVERIFIED_RESEARCH")

    def test_invalid_odds_are_held_without_exceptions(self):
        for value in (None, True, False, "2.10", [], {}, object(), float("nan"),
                      float("inf"), -float("inf"), 10**1000, -10**1000):
            with self.subTest(value_type=type(value).__name__):
                self.assert_hold("ODDS_BELOW_MIN_OR_INVALID", odds=value)

    def test_invalid_probabilities_are_held_without_exceptions(self):
        for value in (None, True, False, ".55", [], {}, object(), float("nan"),
                      float("inf"), -float("inf"), 10**1000, 0, 1, -.1, 1.1):
            with self.subTest(value_type=type(value).__name__):
                self.assert_hold("PROBABILITY_INVALID", win_probability=value)

    def test_missing_or_non_string_source_is_held(self):
        for value in (None, "", " ", "\t\n", 0, 1, True, [], {}, object()):
            with self.subTest(value_type=type(value).__name__):
                self.assert_hold("QUOTE_SOURCE_MISSING", source=value)

    def test_non_positive_ev_remains_hold(self):
        self.assertEqual(MIN_EV, 0.0)
        self.assert_hold("NON_POSITIVE_EV", odds=2, win_probability=.5)
        self.assert_hold("NON_POSITIVE_EV", win_probability=.4)

    def test_tiny_probability_never_emits_infinite_fair_odds(self):
        decision = self.assert_hold(win_probability=5e-324)
        self.assertIsNone(decision.ev)
        self.assertIsNone(decision.fair_odds)

    def test_finite_extreme_arithmetic_stays_finite_and_unverified(self):
        decision = self.decision(odds=1e308, win_probability=1e-307)
        self.assertEqual(decision.status, "UNVERIFIED_RESEARCH")
        self.assertTrue(math.isfinite(decision.ev))
        self.assertTrue(math.isfinite(decision.fair_odds))
        json.dumps(dataclasses.asdict(decision), allow_nan=False)

    def test_false_zero_and_other_non_datetime_now_are_not_defaulted(self):
        for value in (False, 0, 1, "", [], {}, object(), "2026-10-22T12:00:00Z"):
            with self.subTest(value_type=type(value).__name__):
                self.assert_hold("TIMESTAMP_INVALID", now=value)

    def test_none_now_uses_the_current_aware_clock_only(self):
        current = datetime.now(timezone.utc)
        decision = self.decision(
            now=None, quote_at=current-timedelta(minutes=2),
            kickoff_at=current+timedelta(hours=2),
        )
        self.assertEqual(decision.status, "UNVERIFIED_RESEARCH")

    def test_missing_invalid_and_naive_event_times_are_held(self):
        for key in ("quote_at", "kickoff_at"):
            for value in (None, False, 0, "", object(), self.now.replace(tzinfo=None)):
                with self.subTest(key=key, value_type=type(value).__name__):
                    self.assert_hold("TIMESTAMP_INVALID", **{key: value})
        self.assert_hold("TIMESTAMP_INVALID", now=self.now.replace(tzinfo=None))

    def test_broken_timezone_is_held_without_exception(self):
        class BrokenTimezone(tzinfo):
            def utcoffset(self, value):
                raise ValueError("invalid caller timezone")
        broken = datetime(2026, 10, 22, 12, tzinfo=BrokenTimezone())
        for key in ("now", "quote_at", "kickoff_at"):
            with self.subTest(key=key):
                self.assert_hold("TIMESTAMP_INVALID", **{key: broken})

    def test_quote_age_20_minute_boundary_is_inclusive(self):
        self.assertEqual(MAX_QUOTE_AGE_SECONDS, 1200)
        self.assertEqual(
            self.decision(quote_at=self.now-timedelta(seconds=1200)).status,
            "UNVERIFIED_RESEARCH",
        )
        self.assert_hold("QUOTE_STALE_OR_EVENT_STARTED",
                         quote_at=self.now-timedelta(seconds=1200, microseconds=1))

    def test_quote_at_now_is_allowed_but_future_quote_is_held(self):
        self.assertEqual(self.decision(quote_at=self.now).status, "UNVERIFIED_RESEARCH")
        self.assert_hold("QUOTE_STALE_OR_EVENT_STARTED",
                         quote_at=self.now+timedelta(microseconds=1))

    def test_started_or_quote_at_kickoff_is_held(self):
        for kickoff in (self.now, self.now-timedelta(microseconds=1),
                        self.args["quote_at"]):
            with self.subTest(kickoff=kickoff):
                self.assert_hold("QUOTE_STALE_OR_EVENT_STARTED", kickoff_at=kickoff)
        self.assert_hold("QUOTE_STALE_OR_EVENT_STARTED",
                         quote_at=self.args["kickoff_at"])

    def test_aware_offsets_compare_the_same_instants(self):
        hk = timezone(timedelta(hours=8))
        decision = self.decision(
            now=self.now.astimezone(hk),
            quote_at=self.args["quote_at"].astimezone(hk),
            kickoff_at=self.args["kickoff_at"].astimezone(hk),
        )
        self.assertEqual(decision.status, "UNVERIFIED_RESEARCH")

    def test_dst_fold_is_compared_by_utc_instant(self):
        zone = ZoneInfo("America/New_York")
        current = datetime(2026, 11, 1, 1, 20, tzinfo=zone, fold=0)
        future_quote = datetime(2026, 11, 1, 1, 10, tzinfo=zone, fold=1)
        self.assert_hold("QUOTE_STALE_OR_EVENT_STARTED",
                         now=current, quote_at=future_quote,
                         kickoff_at=datetime(2026, 11, 1, 3, 0, tzinfo=zone))


if __name__ == "__main__":
    unittest.main()
