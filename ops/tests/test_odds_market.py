"""Cost-free synthetic tests for The Odds API connector and 500-credit guard."""
import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from odds_market import (SPORTS, MAX_USED, MIN_REMAINING, aggregate, may_spend,
                         book_probabilities, quota, collect, APIProblem)


class MockHeaders(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class FakeResponse:
    def __init__(self, data, headers):
        import json
        self.body = json.dumps(data).encode("utf-8")
        self.headers = MockHeaders(headers)
    def read(self, n):
        return self.body[:n]
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class TestFreeMarketConnector(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 9, 4, tzinfo=timezone.utc)
        self.kickoff = (self.now + timedelta(days=2)).isoformat()
        self.market = {
            "key": "h2h", "last_update": self.now.isoformat(),
            "outcomes": [
                {"name": "Home FC", "price": 2.2},
                {"name": "Draw", "price": 3.3},
                {"name": "Away FC", "price": 3.4}
            ],
        }
        self.event = {"id": "official-123", "home_team": "Home FC",
                      "away_team": "Away FC", "commence_time": self.kickoff,
                      "bookmakers": [{"key": "book_a", "markets": [self.market]},
                                     {"key": "book_b", "markets": [self.market]}]}

    def test_quota_floor(self):
        self.assertTrue(may_spend({"used": 20, "remaining": 480}))
        self.assertFalse(may_spend({"used": MAX_USED, "remaining": 140}))
        self.assertFalse(may_spend({"used": 4, "remaining": MIN_REMAINING}))
        self.assertFalse(may_spend({"used": None, "remaining": 500}))

    def test_quota_missing_headers_stops(self):
        self.assertFalse(may_spend(quota({})))

    def test_quota_malformed_values_fail_closed_without_crashing(self):
        for bad in (None, [], {"used": True, "remaining": 499},
                    {"used": "2", "remaining": 499},
                    {"used": -1, "remaining": 499},
                    {"used": 10, "remaining": float("nan")}):
            with self.subTest(bad=repr(bad)):
                self.assertFalse(may_spend(bad))

    def test_de_vig_probabilities_have_three_outcomes(self):
        result = aggregate(self.event, now=self.now)
        self.assertIsNotNone(result)
        self.assertEqual(result["contributing_bookmakers"], 2)
        self.assertAlmostEqual(sum(result[k] for k in ("p_home", "p_draw", "p_away")), 1, places=5)
        self.assertFalse(result["prediction_or_value_bet"])

    def test_consensus_uses_oldest_book_timestamp(self):
        old = self.now - timedelta(hours=6)
        self.event["bookmakers"][0]["markets"] = [{
            **self.market, "last_update": old.isoformat()
        }]
        result = aggregate(self.event, now=self.now)
        self.assertIsNotNone(result)
        self.assertEqual(result["market_last_update_utc"], old.isoformat())
        self.assertEqual(result["contributing_bookmakers"], 2)

    def test_duplicate_bookmaker_blocks_cannot_steer_consensus(self):
        duplicate = copy.deepcopy(self.event["bookmakers"][0])
        duplicate["markets"][0]["outcomes"][0]["price"] = 9.9
        self.event["bookmakers"].append(duplicate)
        self.assertIsNone(aggregate(self.event, now=self.now))
        self.event["bookmakers"].append({
            "key": "book_c", "markets": [self.market]})
        result = aggregate(self.event, now=self.now)
        self.assertIsNotNone(result)
        self.assertEqual(result["contributing_bookmakers"], 2)

    def test_duplicate_h2h_outcome_rejects_book(self):
        self.event["bookmakers"][0]["markets"] = [copy.deepcopy(self.market)]
        self.event["bookmakers"][0]["markets"][0]["outcomes"].append(
            {"name": "Home FC", "price": 50.0})
        self.assertIsNone(aggregate(self.event, now=self.now))

    def test_book_update_cannot_replace_missing_market_update(self):
        self.event["bookmakers"][0]["markets"] = [copy.deepcopy(self.market)]
        del self.event["bookmakers"][0]["markets"][0]["last_update"]
        self.event["bookmakers"][0]["last_update"] = self.now.isoformat()
        self.assertIsNone(aggregate(self.event, now=self.now))

    def test_single_bookmaker_not_sufficient(self):
        self.event["bookmakers"] = self.event["bookmakers"][:1]
        self.assertIsNone(aggregate(self.event, now=self.now))

    def test_expired_market_excluded(self):
        self.market["last_update"] = (self.now - timedelta(hours=10)).isoformat()
        self.assertIsNone(aggregate(self.event, now=self.now))

    def test_inplay_excluded(self):
        self.event["commence_time"] = (self.now - timedelta(minutes=1)).isoformat()
        self.assertIsNone(aggregate(self.event, now=self.now))

    def test_no_draw_excluded(self):
        self.market["outcomes"] = self.market["outcomes"][:1] + self.market["outcomes"][2:]
        self.assertIsNone(aggregate(self.event, now=self.now))

    def test_key_rejected_before_paid_requests(self):
        from urllib.error import HTTPError
        calls = []
        def fake(request, timeout):
            calls.append(request.full_url.split("?")[0])
            raise HTTPError(request.full_url, 401, "unauthorized", {}, None)
        with self.assertRaisesRegex(APIProblem, "KEY_REJECTED"):
            collect("example-not-real", opener=fake, now=self.now)
        self.assertEqual(len(calls), 1)
        self.assertIn("/sports/", calls[0])
        self.assertNotIn("/odds", calls[0])

    def test_collect_budget_guard_sends_only_free_sports_query(self):
        calls = []
        def fake(request, timeout):
            calls.append(request.full_url.split("?")[0])
            return FakeResponse([{"key": k, "active": True} for k in SPORTS.values()],
                                {"x-requests-used": "360", "x-requests-remaining": "140",
                                 "x-requests-last": "0"})
        result = collect("example-not-real", opener=fake, now=self.now)
        self.assertEqual(result["reason"], "FREE_QUOTA_GUARD")
        self.assertEqual(len(calls), 1)

    def test_collect_filters_mismatched_sport_key(self):
        calls = []
        def fake(request, timeout):
            calls.append(request.full_url.split("?")[0])
            if request.full_url.split("?")[0].endswith("/sports/"):
                return FakeResponse([{"key": k, "active": True} for k in SPORTS.values()],
                                    {"x-requests-used": "0",
                                     "x-requests-remaining": "500", "x-requests-last": "0"})
            wrong = dict(self.event, sport_key="soccer_wrong_league")
            return FakeResponse([wrong], {
                "x-requests-used": str(len(calls)-1),
                "x-requests-remaining": str(501-len(calls)),
                "x-requests-last": "1"})
        result=collect("synthetic-only",opener=fake,now=self.now)
        self.assertEqual(result["event_count"], 0)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(len(calls), 7)

    def test_malformed_sports_catalog_key_fails_closed(self):
        def fake(request, timeout):
            return FakeResponse([{"key": ["unhashable"], "active": True}],
                                {"x-requests-used": "0", "x-requests-remaining": "500",
                                 "x-requests-last": "0"})
        result = collect("synthetic-only", opener=fake, now=self.now)
        self.assertEqual(result["event_count"], 0)
        self.assertEqual(result["status"], "HOLD")

    def test_duplicate_source_event_id_is_quarantined_before_archive(self):
        calls = []
        def fake(request, timeout):
            calls.append(request.full_url.split("?")[0])
            if request.full_url.split("?")[0].endswith("/sports/"):
                return FakeResponse([{"key": k, "active": True} for k in SPORTS.values()],
                                    {"x-requests-used": "0", "x-requests-remaining": "500",
                                     "x-requests-last": "0"})
            return FakeResponse([self.event, copy.deepcopy(self.event)], {
                "x-requests-used": str(len(calls)-1),
                "x-requests-remaining": str(501-len(calls)), "x-requests-last": "1"})
        result = collect("synthetic-only", opener=fake, now=self.now)
        self.assertEqual(result["event_count"], 0)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_collect_only_derived_values_no_raw_prices(self):
        calls = []
        def fake(request, timeout):
            calls.append(request.full_url.split("?")[0])
            if request.full_url.split("?")[0].endswith("/sports/"):
                return FakeResponse([{"key": k, "active": True} for k in SPORTS.values()],
                                    {"x-requests-used": "0", "x-requests-remaining": "500", "x-requests-last": "0"})
            used = len(calls) - 1
            return FakeResponse([self.event], {"x-requests-used": str(used),
                                               "x-requests-remaining": str(500 - used),
                                               "x-requests-last": "1"})
        result = collect("example-not-real", opener=fake, now=self.now)
        self.assertEqual(len(calls), 7)
        self.assertEqual(result["event_count"], 6)
        self.assertEqual(result["quota"]["remaining"], 494)
        self.assertEqual(result["production_recommendations"], "DISABLED")
        for item in result["events"]:
            self.assertNotIn("bookmakers", item)
            self.assertNotIn("markets", item)
            self.assertNotIn("price", item)
            self.assertNotIn("book", item)
            self.assertIn("contributing_bookmakers", item)


    def test_malformed_bookmaker_list_is_nonfatal(self):
        self.event["bookmakers"] = {"unexpected": "structure"}
        self.assertIsNone(aggregate(self.event, now=self.now))

    def test_malformed_market_or_outcome_lists_are_nonfatal(self):
        self.event["bookmakers"][0]["markets"] = {"unexpected": []}
        self.assertIsNone(aggregate(self.event, now=self.now))
        self.event["bookmakers"][0]["markets"] = [{**self.market, "outcomes": None}]
        self.assertIsNone(aggregate(self.event, now=self.now))

if __name__ == "__main__":
    unittest.main()
