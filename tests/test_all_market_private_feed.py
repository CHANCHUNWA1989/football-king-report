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
    return {"id": "event1", "sport_key": "soccer_epl", "home_team": "Home", "away_team": "Away",
            "commence_time": (NOW + timedelta(hours=2)).isoformat(),
            "bookmakers": [{"key": "book1", "markets": [
                {"key": "h2h", "last_update": (NOW - timedelta(minutes=2)).isoformat(),
                 "outcomes": [{"name": "Home", "price": 2.1},
                              {"name": "Draw", "price": 3.3},
                              {"name": "Away", "price": 3.4}]},
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
        self.assertEqual(len(result["quotes"]), 3)
        self.assertEqual(result["collector_status"], "CONNECTED")
        self.assertTrue(all(not x["independently_calibrated"] for x in result["quotes"]))
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertTrue(all(x["captured_utc"] == NOW.isoformat() for x in result["quotes"]))
        self.assertTrue(all(x["observed_utc"] == (NOW-timedelta(minutes=2)).isoformat()
                            for x in result["quotes"]))

    @patch("ops.all_market_private_feed.datetime")
    @patch("ops.all_market_private_feed.retrieve")
    @patch("ops.all_market_private_feed.verify")
    def test_new_quote_during_slow_request_is_not_mistaken_for_future(self, verify, retrieve, clock):
        verify.return_value = catalogue()
        clock.now.return_value = NOW
        completed = NOW + timedelta(seconds=90)
        event = fixture()
        event["bookmakers"][0]["markets"][0]["last_update"] = completed.isoformat()
        def response(*args, **kwargs):
            clock.now.return_value = completed
            return [event], {"used": 4, "remaining": 497}
        retrieve.side_effect = response
        result = collect("test-key")
        self.assertEqual(len(result["quotes"]), 3)
        self.assertTrue(all(q["captured_utc"] == completed.isoformat() for q in result["quotes"]))
        self.assertTrue(all(q["observed_utc"] == completed.isoformat() for q in result["quotes"]))

    @patch("ops.all_market_private_feed.datetime")
    @patch("ops.all_market_private_feed.retrieve")
    @patch("ops.all_market_private_feed.verify")
    def test_quote_expiring_during_request_is_rejected(self, verify, retrieve, clock):
        verify.return_value = catalogue()
        clock.now.return_value = NOW
        event = fixture()
        event["bookmakers"][0]["markets"][0]["last_update"] = (
            NOW - timedelta(minutes=19)).isoformat()
        def response(*args, **kwargs):
            clock.now.return_value = NOW + timedelta(minutes=2)
            return [event], {"used": 4, "remaining": 497}
        retrieve.side_effect = response
        self.assertEqual(collect("test-key")["quotes"], [])

    @patch("ops.all_market_private_feed.datetime")
    @patch("ops.all_market_private_feed.retrieve")
    @patch("ops.all_market_private_feed.verify")
    def test_kickoff_buffer_uses_completed_response_clock(self, verify, retrieve, clock):
        verify.return_value = catalogue()
        clock.now.return_value = NOW
        event = fixture()
        event["commence_time"] = (NOW + timedelta(minutes=11)).isoformat()
        def response(*args, **kwargs):
            clock.now.return_value = NOW + timedelta(minutes=2)
            return [event], {"used": 4, "remaining": 497}
        retrieve.side_effect = response
        self.assertEqual(collect("test-key")["quotes"], [])

    @patch("ops.all_market_private_feed.datetime")
    @patch("ops.all_market_private_feed.retrieve")
    @patch("ops.all_market_private_feed.verify")
    def test_each_league_keeps_its_own_response_capture_time(self, verify, retrieve, clock):
        catalog = catalogue()
        catalog["supported"]["championship"] = True
        catalog["active"]["championship"] = True
        verify.return_value = catalog
        clock.now.return_value = NOW
        completed = [NOW + timedelta(minutes=1), NOW + timedelta(minutes=3)]
        def response(*args, **kwargs):
            clock.now.return_value = completed[retrieve.call_count-1]
            event = fixture()
            event["sport_key"] = args[0].split("/")[2]
            return [event], {"used": 4 + retrieve.call_count, "remaining": 490}
        retrieve.side_effect = response
        result = collect("test-key")
        self.assertEqual(retrieve.call_count, 2)
        self.assertEqual(len(result["quotes"]), 6)
        self.assertEqual({q["captured_utc"] for q in result["quotes"]
                          if q["league"] == "epl"}, {completed[0].isoformat()})
        self.assertEqual({q["captured_utc"] for q in result["quotes"]
                          if q["league"] == "championship"}, {completed[1].isoformat()})

    @patch("ops.all_market_private_feed.retrieve")
    @patch("ops.all_market_private_feed.verify")
    def test_invalid_explicit_clock_fails_before_api_access(self, verify, retrieve):
        for invalid in (False, 0, "", NOW.replace(tzinfo=None)):
            with self.subTest(now=invalid), self.assertRaisesRegex(ValueError, "INVALID_COLLECTION_CLOCK"):
                collect("test-key", now=invalid)
        verify.assert_not_called()
        retrieve.assert_not_called()

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
