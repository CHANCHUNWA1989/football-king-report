"""Zero-credit contract tests for optional 5DollarFootballAPI free adapter."""
import copy
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from five_dollar_free import collect, parse_fixture_list, valid_three_way

NOW = datetime(2026, 10, 9, 8, tzinfo=timezone.utc)


class Response:
    headers = {"X-RateLimit-Remaining": "52"}
    def __init__(self, value):
        self.raw = json.dumps(value).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size):
        return self.raw[:size]


def payloads():
    fixture = {"id": 12, "status": "scheduled", "league": {"name": "Premier League"},
               "teams": {"home": {"name": "Everton"}, "away": {"name": "Arsenal"}},
               "kickoff_utc": (NOW + timedelta(days=2)).isoformat()}
    odds = {"success": 1, "data": {
        "fixture_id": 12,
        "bookmakers": [{"slug": "bet365", "odds": {
            "1x2": {"opening": {"home": 2.8, "draw": 3.3, "away": 2.5},
                    "closing": None, "inplay": None}}}]}}
    return [{"success": 1, "data": {"plan": "free"}},
            {"success": 1, "data": [fixture]}, odds]


class FreeFiveDollarTests(unittest.TestCase):
    def test_missing_key_costs_zero_and_is_not_ready(self):
        state = collect(key="", now=NOW)
        self.assertEqual(state["calls_attempted"], 0)
        self.assertEqual(state["status"], "NOT_CONFIGURED")
        self.assertFalse(state["safe_primary_odds_fallback"])

    def test_one_verified_shape_uses_only_three_calls(self):
        values = payloads()
        urls = []
        def requester(req, timeout):
            urls.append(req.full_url)
            self.assertEqual(req.get_header("Authorization"), "Bearer test-not-secret")
            return Response(values[len(urls)-1])
        result = collect(key="test-not-secret", now=NOW, requester=requester)
        self.assertEqual(result["calls_attempted"], 3)
        self.assertEqual(result["eligible_fixture_sample_count"], 1)
        self.assertTrue(result["one_book_1x2_sample_available"])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["safe_primary_odds_fallback"])
        self.assertFalse(result["point_in_time_market_verified"])
        self.assertNotIn("test-not-secret", json.dumps(result))
        self.assertNotIn("2.8", json.dumps(result))
        self.assertTrue(all("test-not-secret" not in url for url in urls))

    def test_inplay_or_unknown_fixture_is_not_eligible(self):
        fixture=payloads()[1]["data"][0]
        fixture["status"]="in_play"
        self.assertEqual(parse_fixture_list({"success":1,"data":[fixture]},NOW),[])

    def test_future_and_missing_time_excluded(self):
        fixture=payloads()[1]["data"][0]
        fixture["kickoff_utc"]="not-a-date"
        self.assertEqual(parse_fixture_list({"success":1,"data":[fixture]},NOW),[])
        fixture["kickoff_utc"]=(NOW-timedelta(hours=1)).isoformat()
        self.assertEqual(parse_fixture_list({"success":1,"data":[fixture]},NOW),[])

    def test_unsafe_price_or_wrong_book_rejected(self):
        odds=payloads()[-1]
        odds["data"]["bookmakers"][0]["odds"]["1x2"]["opening"]["home"]=-1
        self.assertFalse(valid_three_way(odds,12))
        odds["data"]["bookmakers"][0]["odds"]["1x2"]["opening"]["home"]=2.8
        odds["data"]["bookmakers"][0]["slug"]="not-free"
        self.assertFalse(valid_three_way(odds,12))

    def test_invalid_plan_stops_after_one_request(self):
        urls=[]
        def fake(req,timeout):
            urls.append(req.full_url)
            return Response({"success":1,"data":{"plan":"pro"}})
        result=collect(key="example",now=NOW,requester=fake)
        self.assertEqual(result["calls_attempted"],1)
        self.assertEqual(result["reason"],"UNKNOWN_OR_NOT_FREE_PLAN")
        self.assertFalse(result["one_book_1x2_sample_available"])

    def test_provider_rate_limit_fails_closed(self):
        calls=[]
        def fake(req,timeout):
            calls.append(req.full_url)
            raise HTTPError(req.full_url,429,"rate limited",{},None)
        r=collect(key="example",now=NOW,requester=fake)
        self.assertEqual(r["calls_attempted"],1)
        self.assertEqual(r["reason"],"QUOTA_EXHAUSTED")
        self.assertEqual(r["production_recommendations"],"DISABLED")


if __name__=="__main__":
    unittest.main()
