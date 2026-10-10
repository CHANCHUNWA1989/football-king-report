import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
from ops.all_market_private_feed import collect, main
from ops.odds_market import APIProblem

NOW = datetime(2026, 10, 10, 10, tzinfo=timezone.utc)

def fixture():
    return {"id": "event1", "home_team": "Home", "away_team": "Away",
            "commence_time": (NOW + timedelta(hours=2)).isoformat(),
            "bookmakers": [{"key": "book1", "markets": [
                {"key": "h2h", "last_update": (NOW - timedelta(minutes=2)).isoformat(),
                 "outcomes": [{"name": "Home", "price": 2.1},
                              {"name": "Draw", "price": 3.3}]},
                {"key": "spreads", "last_update": (NOW - timedelta(minutes=2)).isoformat(),
                 "outcomes": [{"name": "Away", "point": 0.75, "price": 1.9}]},
                {"key": "totals", "last_update": (NOW - timedelta(minutes=30)).isoformat(),
                 "outcomes": [{"name": "Over", "point": 2.5, "price": 1.9}]}]}]}

def catalogue(used=1, remaining=500):
    return {"quota": {"used": used, "remaining": remaining},
            "supported": {"epl": True}, "active": {"epl": True}}

class FeedTest(unittest.TestCase):
    @patch("ops.all_market_private_feed.retrieve")
    @patch("ops.all_market_private_feed.verify")
    def test_only_requested_h2h_and_staleness(self, verify, retrieve):
        verify.return_value = catalogue()
        retrieve.return_value = ([fixture()], {"used": 4, "remaining": 497})
        result = collect("test-key", now=NOW)
        self.assertEqual({x["market"] for x in result["quotes"]}, {"h2h"})
        self.assertEqual(retrieve.call_args.kwargs["params"]["markets"], "h2h")
        self.assertEqual(len(result["quotes"]), 2)
        self.assertEqual(result["collector_status"], "CONNECTED")
        self.assertTrue(all(not x["independently_calibrated"] for x in result["quotes"]))
        self.assertEqual(result["production_recommendations"], "DISABLED")

    @patch("ops.all_market_private_feed.retrieve")
    @patch("ops.all_market_private_feed.verify")
    def test_quota_guard_prevents_requests(self, verify, retrieve):
        verify.return_value = catalogue(359, 140)
        result = collect("test-key", now=NOW)
        self.assertEqual(result["quotes"], [])
        self.assertEqual(result["collector_status"], "QUOTA_GUARD")
        retrieve.assert_not_called()

    @patch("ops.all_market_private_feed.retrieve")
    @patch("ops.all_market_private_feed.verify")
    def test_auth_failure_is_not_connected(self, verify, retrieve):
        verify.return_value = catalogue()
        retrieve.side_effect = APIProblem("KEY_REJECTED_OR_NOT_AUTHORIZED")
        result = collect("test-key", now=NOW)
        self.assertEqual(result["collector_status"], "PROVIDER_ERROR")
        self.assertEqual(result["quotes"], [])
        self.assertEqual(result["collector_reason"], "KEY_REJECTED_OR_NOT_AUTHORIZED")

    def test_missing_key_writes_machine_readable_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            try:
                os.chdir(tmp)
                with patch.dict(os.environ, {"THE_ODDS_API_KEY": ""}):
                    main()
                report = json.loads(Path("output/private_all_market_quotes.json").read_text())
                self.assertEqual(report["collector_status"], "MISSING_API_KEY")
                self.assertEqual(report["production_recommendations"], "DISABLED")
            finally:
                os.chdir(cwd)

if __name__ == "__main__":
    unittest.main()
