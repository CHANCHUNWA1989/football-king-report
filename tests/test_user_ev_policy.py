import unittest
from datetime import datetime, timedelta, timezone
from ops.user_ev_policy import evaluate_binary_market

class EVPolicyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
        self.args = dict(odds=2.10, win_probability=.55, source="user_platform_screenshot",
                         quote_at=self.now-timedelta(minutes=2),
                         kickoff_at=self.now+timedelta(hours=2),
                         model_calibrated=True, model_validated=True,
                         identity_verified=True, now=self.now)
    def check(self, reason, **changes):
        args = dict(self.args, **changes)
        self.assertEqual(evaluate_binary_market(**args).reason, reason)
    def test_positive(self):
        d = evaluate_binary_market(**self.args)
        self.assertEqual(d.status, "ELIGIBLE_RESEARCH")
        self.assertAlmostEqual(d.ev, .155)
    def test_min_odds(self):
        self.check("ODDS_BELOW_MIN_OR_INVALID", odds=1.79)
    def test_uncalibrated(self):
        self.check("MODEL_NOT_INDEPENDENTLY_VALIDATED", model_calibrated=False)
    def test_bad_identity(self):
        self.check("EVENT_MARKET_IDENTITY_UNVERIFIED", identity_verified=False)
    def test_stale(self):
        self.check("QUOTE_STALE_OR_EVENT_STARTED", quote_at=self.now-timedelta(hours=1))
    def test_no_edge(self):
        self.check("NON_POSITIVE_EV", win_probability=.40)
    def test_missing_source(self):
        self.check("QUOTE_SOURCE_MISSING", source="")
    def test_started(self):
        self.check("QUOTE_STALE_OR_EVENT_STARTED", kickoff_at=self.now)
if __name__ == "__main__":
    unittest.main()
