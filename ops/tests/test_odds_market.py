"""Cost-free synthetic tests for The Odds API connector and 500-credit guard."""
import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from odds_market import (SPORTS, MAX_USED, MIN_REMAINING, aggregate, may_spend,
                         book_probabilities, quota, collect, APIProblem, utc)


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

    def test_collect_normalizes_non_utc_clock(self):
        from odds_market import collect
        from datetime import timezone, timedelta
        class EmptyCatalog:
            headers = {"x-requests-used": "0", "x-requests-remaining": "500", "x-requests-last": "0"}
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n): return b"[]"
        result = collect("fake-key", opener=lambda request, timeout: EmptyCatalog(),
                         now=self.now.astimezone(timezone(timedelta(hours=8))))
        self.assertEqual(result["as_of_utc"], self.now.isoformat())
        self.assertEqual(result["status"], "HOLD")

    def test_bad_provider_timestamps_fail_closed(self):
        for value in (None, 0, [], {}, "", "not-a-date", "2026-10-09T12:00:00"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                utc(value)
        self.assertEqual(utc("2026-10-09T12:00:00Z"),
                         datetime(2026, 10, 9, 12, tzinfo=timezone.utc))

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

    def test_power_normalization_matches_exact_squared_inverse_case(self):
        # q=(99,12,16)/101 has sum(q**2)=1, so the power is exactly 2.
        market=copy.deepcopy(self.market)
        for outcome,price in zip(market["outcomes"],(101/99,101/12,101/16)):
            outcome["price"]=price
        book={"key":"synthetic-book","markets":[market]}
        probabilities,_=book_probabilities(book,"Home FC","Away FC",self.now,
                                          normalization="power")
        for actual,expected in zip(probabilities,(9801/10201,144/10201,256/10201)):
            self.assertAlmostEqual(actual,expected,places=10)
        baseline,_=book_probabilities(book,"Home FC","Away FC",self.now)
        for actual,expected in zip(baseline,(99/127,12/127,16/127)):
            self.assertAlmostEqual(actual,expected,places=12)

    def test_power_handles_fair_underround_and_extreme_valid_prices(self):
        for prices in ((2.,4.,4.),(2.02,4.04,4.04),(1.01,500.,500.)):
            with self.subTest(prices=prices):
                market=copy.deepcopy(self.market)
                for outcome,price in zip(market["outcomes"],prices):
                    outcome["price"]=price
                book={"key":"synthetic-book","markets":[market]}
                result=book_probabilities(book,"Home FC","Away FC",self.now,
                                          normalization="power")
                self.assertIsNotNone(result)
                probabilities,_=result
                self.assertAlmostEqual(sum(probabilities),1.,places=12)
                self.assertTrue(all(0<=value<=1 for value in probabilities))
                self.assertAlmostEqual(probabilities[1],probabilities[2],places=12)
                if prices==(2.,4.,4.):
                    for actual,expected in zip(probabilities,(.5,.25,.25)):
                        self.assertAlmostEqual(actual,expected,places=12)
                else:
                    self.assertTrue(all(p>=1/price for p,price in zip(probabilities,prices)))

    def test_power_reuses_invalid_price_and_timestamp_rejection(self):
        variants=[{"last_update":None},{"last_update":(self.now-timedelta(hours=9)).isoformat()},
                  {"last_update":(self.now+timedelta(minutes=6)).isoformat()}]
        for price in (True,0,-1,float("nan"),float("inf"),"2.2"):
            market=copy.deepcopy(self.market)
            market["outcomes"][0]["price"]=price
            variants.append(market)
        for variant in variants:
            with self.subTest(variant=variant):
                book={"key":"synthetic-book","markets":[{**self.market,**variant}]}
                self.assertIsNone(book_probabilities(book,"Home FC","Away FC",self.now,
                                                     normalization="power"))
        with self.assertRaises(ValueError):
            book_probabilities(self.event["bookmakers"][0],"Home FC","Away FC",self.now,
                               normalization="unknown")

    def test_same_book_sensitivity_is_derived_only_and_keeps_existing_baseline(self):
        before=copy.deepcopy(self.event)
        result=aggregate(self.event,now=self.now)
        self.assertIn("normalization_sensitivity",result)
        audit=result["normalization_sensitivity"]
        self.assertEqual(audit["baseline_method"],"multiplicative")
        self.assertEqual(audit["alternative_method"],"power")
        self.assertEqual(audit["same_bookmaker_count"],2)
        self.assertGreater(audit["max_absolute_probability_difference"],0)
        alternate=audit["alternative_consensus"]
        self.assertAlmostEqual(sum(alternate.values()),1.,places=6)
        inverse=(1/2.2,1/3.3,1/3.4)
        for name,value in zip(("p_home","p_draw","p_away"),inverse):
            self.assertEqual(result[name],round(value/sum(inverse),7))
        self.assertFalse(audit["calibration_verified"])
        self.assertFalse(audit["positive_ev_verified"])
        self.assertEqual(audit["production_recommendations"],"DISABLED")
        self.assertIsNone(audit["recommendation"])
        self.assertFalse(result["prediction_or_value_bet"])
        self.assertEqual(self.event,before)

    def test_sensitivity_excludes_duplicate_and_stale_bookmakers(self):
        self.event["bookmakers"].append(copy.deepcopy(self.event["bookmakers"][0]))
        self.event["bookmakers"].append({"key":"book_c","markets":[self.market]})
        stale={**self.market,"last_update":(self.now-timedelta(hours=9)).isoformat()}
        self.event["bookmakers"].append({"key":"book_stale","markets":[stale]})
        result=aggregate(self.event,now=self.now)
        self.assertIn("normalization_sensitivity",result)
        self.assertEqual(result["contributing_bookmakers"],2)
        self.assertEqual(result["normalization_sensitivity"]["same_bookmaker_count"],2)

    def test_sensitivity_uses_same_three_books_and_normalizes_their_medians(self):
        books=[]
        for index,denominators in enumerate(((99,12,16),(99,16,12),(12,99,16))):
            market=copy.deepcopy(self.market)
            for outcome,denominator in zip(market["outcomes"],denominators):
                outcome["price"]=101/denominator
            if index==2:
                market["last_update"]=(self.now-timedelta(hours=6)).isoformat()
            books.append({"key":f"synthetic-{index}","markets":[market]})
        self.event["bookmakers"]=books
        result=aggregate(self.event,now=self.now)
        self.assertIn("normalization_sensitivity",result)
        audit=result["normalization_sensitivity"]
        self.assertEqual(audit["same_bookmaker_count"],3)
        # Per-book powers are 2; medians are proportional to (99**2,16**2,16**2).
        for name,numerator in zip(("p_home","p_draw","p_away"),(9801,256,256)):
            self.assertEqual(audit["alternative_consensus"][name],round(numerator/10313,7))
        for name,numerator in zip(("p_home","p_draw","p_away"),(99,16,16)):
            self.assertEqual(result[name],round(numerator/131,7))
        self.assertEqual(result["market_last_update_utc"],
                         (self.now-timedelta(hours=6)).isoformat())

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
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertEqual(result["requested_markets"], ["h2h"])
        self.assertEqual(result["missing_markets"], ["spreads", "totals"])
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
            self.assertIn("normalization_sensitivity",item)
            self.assertEqual(item["normalization_sensitivity"]["same_bookmaker_count"],2)
            self.assertFalse(item["normalization_sensitivity"]["positive_ev_verified"])
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
