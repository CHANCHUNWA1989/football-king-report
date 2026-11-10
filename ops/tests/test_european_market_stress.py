"""Stress the actual 1X2 aggregation logic with synthetic bookmaker feeds."""
import copy
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from ops.odds_market import aggregate


NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)


def fixture():
    def book(key):
        return {"key": key, "markets": [{
            "key": "h2h", "last_update": (NOW - timedelta(minutes=3)).isoformat(),
            "outcomes": [
                {"name": "Home FC", "price": 2.3},
                {"name": "Draw", "price": 3.4},
                {"name": "Away FC", "price": 3.6},
            ],
        }]}
    return {
        "id": "fixture-1", "home_team": "Home FC", "away_team": "Away FC",
        "commence_time": (NOW + timedelta(hours=4)).isoformat(),
        "bookmakers": [book("book_a"), book("book_b")],
    }


class TestEuropeanMarketStress(unittest.TestCase):
    def test_2000_parallel_consensus_calculations(self):
        event = fixture()
        with ThreadPoolExecutor(max_workers=32) as pool:
            rows = list(pool.map(lambda _: aggregate(event, now=NOW), range(2000)))
        self.assertEqual(len(rows), 2000)
        self.assertTrue(all(row == rows[0] for row in rows))
        self.assertEqual(rows[0]["contributing_bookmakers"], 2)
        self.assertAlmostEqual(sum(rows[0][k] for k in ("p_home", "p_draw", "p_away")), 1, places=5)
        self.assertFalse(rows[0]["prediction_or_value_bet"])

    def test_duplicate_bookmaker_and_stale_market_rejected(self):
        duplicate = fixture()
        duplicate["bookmakers"].append(copy.deepcopy(duplicate["bookmakers"][0]))
        self.assertIsNone(aggregate(duplicate, now=NOW))
        stale = fixture()
        stale["bookmakers"][1]["markets"][0]["last_update"] = (NOW - timedelta(hours=10)).isoformat()
        self.assertIsNone(aggregate(stale, now=NOW))

    def test_bad_prices_and_in_play_rejected(self):
        bad = fixture()
        bad["bookmakers"][0]["markets"][0]["outcomes"][0]["price"] = float("nan")
        self.assertIsNone(aggregate(bad, now=NOW))
        started = fixture()
        started["commence_time"] = (NOW - timedelta(minutes=1)).isoformat()
        self.assertIsNone(aggregate(started, now=NOW))


if __name__ == "__main__":
    unittest.main()
