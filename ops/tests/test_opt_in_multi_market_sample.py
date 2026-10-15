import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from opt_in_multi_market_sample import collect_sample

NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


class OptInMultiMarketSampleTests(unittest.TestCase):
    def test_quota_reserve_prevents_paid_odds_request(self):
        with patch("opt_in_multi_market_sample.verify", return_value={
            "quota": {"used": 100, "remaining": 145},
            "supported": {"epl": True}, "active": {"epl": True},
        }), patch("opt_in_multi_market_sample.retrieve") as retrieve:
            result = collect_sample("fake-key", "epl", now=NOW)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "QUOTA_RESERVE")
        retrieve.assert_not_called()

    def test_missing_quota_headers_fail_closed(self):
        with patch("opt_in_multi_market_sample.verify", return_value={
            "quota": {"used": 100, "remaining": 250},
            "supported": {"epl": True}, "active": {"epl": True},
        }), patch("opt_in_multi_market_sample.retrieve", return_value=(
            [], {"used": None, "remaining": None, "last": None}
        )):
            result = collect_sample("fake-key", "epl", now=NOW)
        self.assertEqual(result["reason"], "MISSING_QUOTA_HEADERS")

    def test_single_league_and_three_markets(self):
        with patch("opt_in_multi_market_sample.verify", return_value={
            "quota": {"used": 100, "remaining": 250},
            "supported": {"epl": True}, "active": {"epl": True},
        }), patch("opt_in_multi_market_sample.retrieve", return_value=(
            [], {"used": 103, "remaining": 247, "last": 3}
        )) as retrieve:
            result = collect_sample("fake-key", "epl", now=NOW)
        self.assertEqual(result["status"], "HOLD")
        kwargs = retrieve.call_args.kwargs
        self.assertEqual(kwargs["params"]["markets"], "h2h,spreads,totals")
        self.assertEqual(kwargs["params"]["regions"], "eu")
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_invalid_league_never_calls_provider(self):
        with patch("opt_in_multi_market_sample.verify") as verify:
            with self.assertRaises(ValueError):
                collect_sample("fake-key", "unknown", now=NOW)
        verify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
