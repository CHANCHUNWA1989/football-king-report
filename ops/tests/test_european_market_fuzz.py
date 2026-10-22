"""Deterministic malformed-feed fuzz regression for 1X2 aggregator (offline)."""
import copy
import random
import unittest

from ops.odds_market import aggregate
from ops.tests.test_european_market_stress import NOW, fixture


class TestEuropeanMarketFuzz(unittest.TestCase):
    def test_5000_mutated_provider_events_never_crash_or_enable_betting(self):
        rng = random.Random(20261023)
        invalid = [None, True, False, 0, -1, 3.14159, "", [], {},
                   {"key": "h2h"}, float("nan"), "not-a-time"]
        base = fixture()
        paths = [
            ("home_team",), ("away_team",), ("id",), ("commence_time",),
            ("bookmakers",), ("bookmakers", 0), ("bookmakers", 0, "key"),
            ("bookmakers", 0, "markets"), ("bookmakers", 0, "markets", 0),
            ("bookmakers", 0, "markets", 0, "last_update"),
            ("bookmakers", 0, "markets", 0, "outcomes"),
            ("bookmakers", 0, "markets", 0, "outcomes", 0),
            ("bookmakers", 0, "markets", 0, "outcomes", 0, "price"),
        ]
        for i in range(5000):
            event = copy.deepcopy(base)
            path = paths[rng.randrange(len(paths))]
            target = event
            for part in path[:-1]:
                target = target[part]
            target[path[-1]] = invalid[rng.randrange(len(invalid))]
            try:
                result = aggregate(event, now=NOW)
            except Exception as exc:
                self.fail(f"Malformed event #{i} crashed: {type(exc).__name__}")
            if result is not None:
                self.assertFalse(result["prediction_or_value_bet"])
                self.assertEqual(result["contributing_bookmakers"], 2)
                self.assertAlmostEqual(
                    sum(result[k] for k in ("p_home", "p_draw", "p_away")),
                    1, places=5)


if __name__ == "__main__":
    unittest.main()
