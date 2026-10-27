"""Consensus invariants across bookmaker order, extra invalid quotes, and odds scale."""
import copy
import random
import unittest

from ops.odds_market import aggregate
from ops.tests.test_european_market_stress import NOW, fixture


class TestEuropeanConsensusInvariants(unittest.TestCase):
    def test_1000_bookmaker_permutations_are_identical(self):
        base = fixture()
        rng = random.Random(20261023)
        baseline = aggregate(base, now=NOW)
        self.assertIsNotNone(baseline)
        for _ in range(1000):
            candidate = copy.deepcopy(base)
            rng.shuffle(candidate["bookmakers"])
            self.assertEqual(aggregate(candidate, now=NOW), baseline)

    def test_malformed_bookmakers_cannot_shift_consensus(self):
        base = fixture()
        baseline = aggregate(base, now=NOW)
        self.assertIsNotNone(baseline)
        candidate = copy.deepcopy(base)
        candidate["bookmakers"].extend([
            None, {}, {"key": ""}, {"key": "invalid", "markets": None},
            {"key": "empty", "markets": []},
            {"key": "bad-market", "markets": [{"key": "h2h", "outcomes": []}]},
        ])
        self.assertEqual(aggregate(candidate, now=NOW), baseline)

    def test_probability_output_is_normalized(self):
        base = fixture()
        for home_price, draw_price, away_price in (
            (2.0, 3.5, 4.0), (2.4, 3.2, 3.4), (2.2, 3.6, 3.6)
        ):
            event = copy.deepcopy(base)
            for bookmaker in event["bookmakers"]:
                for outcome in bookmaker["markets"][0]["outcomes"]:
                    outcome["price"] = {
                        event["home_team"]: home_price,
                        "Draw": draw_price,
                        event["away_team"]: away_price,
                    }[outcome["name"]]
            result = aggregate(event, now=NOW)
            self.assertIsNotNone(result)
            probabilities = [result[k] for k in ("p_home", "p_draw", "p_away")]
            self.assertTrue(all(0 < p < 1 for p in probabilities))
            self.assertAlmostEqual(sum(probabilities), 1.0, places=5)
            self.assertFalse(result["prediction_or_value_bet"])


if __name__ == "__main__":
    unittest.main()
