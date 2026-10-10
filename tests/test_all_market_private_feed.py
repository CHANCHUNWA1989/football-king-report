import unittest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
from ops.all_market_private_feed import collect

NOW = datetime(2026, 10, 10, 10, tzinfo=timezone.utc)
def iso(d):
    return d.isoformat()

def fixture():
    return {"id": "event1", "home_team": "Home", "away_team": "Away",
            "commence_time": iso(NOW+timedelta(hours=2)),
            "bookmakers": [{"key": "book1", "markets": [
                {"key": "h2h", "last_update": iso(NOW-timedelta(minutes=2)),
                 "outcomes": [{"name": "Home", "price": 2.1}, {"name": "Draw", "price": 3.3}]},
                {"key": "spreads", "last_update": iso(NOW-timedelta(minutes=2)),
                 "outcomes": [{"name": "Away", "point": 0.75, "price": 1.9}]},
                {"key": "totals", "last_update": iso(NOW-timedelta(minutes=30)),
                 "outcomes": [{"name": "Over", "point": 2.5, "price": 1.9}]}]}]}

class FeedTest(unittest.TestCase):
    @patch("ops.all_market_private_feed.retrieve")
    @patch("ops.all_market_private_feed.verify")
    def test_market_types_and_staleness(self, verify, retrieve):
        verify.return_value = {"quota": {"used": 1, "remaining": 500},
                               "supported": {"epl": True}, "active": {"epl": True}}
        retrieve.return_value = ([fixture()], {"used": 4, "remaining": 497})
        result = collect("test-key", now=NOW)
        self.assertEqual({x["market"] for x in result["quotes"]}, {"h2h", "spreads"})\n        self.assertEqual(retrieve.call_args.kwargs["params"]["markets"], "h2h")
        self.assertEqual(len(result["quotes"]), 3)
        self.assertTrue(all(not x["independently_calibrated"] for x in result["quotes"]))
        self.assertEqual(result["production_recommendations"], "DISABLED")
    @patch("ops.all_market_private_feed.retrieve")
    @patch("ops.all_market_private_feed.verify")
    def test_quota_guard_prevents_requests(self, verify, retrieve):
        verify.return_value = {"quota": {"used": 359, "remaining": 140},
                               "supported": {"epl": True}, "active": {"epl": True}}
        self.assertEqual(collect("test-key", now=NOW)["quotes"], [])
        retrieve.assert_not_called()

if __name__ == "__main__":
    unittest.main()
