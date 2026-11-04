"""Reproducible high-volume 1X2 compute benchmark with correctness assertions."""
import copy
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from ops.odds_market import aggregate
from ops.tests.test_european_market_stress import NOW, fixture


class TestEuropeanMarketThroughput(unittest.TestCase):
    def test_10000_valid_1x2_calculations(self):
        base = fixture()
        events = []
        for i in range(10000):
            event = copy.deepcopy(base)
            event["id"] = "throughput-" + str(i)
            events.append(event)
        started = time.perf_counter()
        results = [aggregate(event, now=NOW) for event in events]
        elapsed = time.perf_counter() - started
        self.assertEqual(len(results), 10000)
        self.assertTrue(all(r is not None and not r["prediction_or_value_bet"]
                            and r["contributing_bookmakers"] == 2 for r in results))
        self.assertEqual(len({r["source_event_id"] for r in results}), 10000)
        print(f"market_1x2_10000_valid_aggregations_seconds={elapsed:.3f}")

    def test_32_worker_parallel_aggregation_consistency(self):
        base = fixture()
        events = []
        for i in range(2048):
            event = copy.deepcopy(base)
            event["id"] = "parallel-" + str(i)
            events.append(event)
        expected = [aggregate(event, now=NOW) for event in events]
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=32) as pool:
            actual = list(pool.map(lambda event: aggregate(event, now=NOW), events))
        elapsed = time.perf_counter() - started
        self.assertEqual(actual, expected)
        self.assertTrue(all(not r["prediction_or_value_bet"] for r in actual))
        print(f"market_1x2_2048_parallel_32workers_seconds={elapsed:.3f}")


if __name__ == "__main__":
    unittest.main()
