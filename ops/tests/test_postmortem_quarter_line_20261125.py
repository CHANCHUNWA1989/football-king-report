"""Offline settlement regression from 2026-11-25 HKT postmortem.

Scores/lines/prices are scenario inputs, not authenticated match records.
No forecast reconstruction, EV, calibration, or production authorization.
"""
import unittest
from fractions import Fraction
from ops.postmortem_live_diagnostic import settlement_consistency
from ops.live_market_research import payout


class PostmortemQuarterLineRegression(unittest.TestCase):
    def test_deep_handicap_scenarios(self):
        cases = [
            (2, 2, "HOME", -1.75, 1.97, "FULL_LOSS", -1),
            (2, 2, "AWAY", 1.75, 1.92, "FULL_WIN", .92),
            (1, 1, "HOME", -1.25, 2.01, "FULL_LOSS", -1),
            (1, 1, "AWAY", 1.25, 1.88, "FULL_WIN", .88),
            (3, 1, "AWAY", .5, 1.98, "FULL_LOSS", -1),
            (2, 1, "HOME", -1.25, 2, "HALF_LOSS", -.5),
            (2, 1, "AWAY", 1.25, 2, "HALF_WIN", .5),
            (3, 1, "HOME", -1.75, 2, "HALF_WIN", .5),
            (3, 1, "AWAY", 1.75, 2, "HALF_LOSS", -.5),
        ]
        for h, a, side, line, odds, grade, expected in cases:
            with self.subTest(h=h, a=a, side=side, line=line):
                actual, profit = settlement_consistency(h, a, side, line, odds)
                self.assertEqual(actual, grade)
                self.assertAlmostEqual(profit, expected, places=12)

    def test_totals_275_and_325_boundaries(self):
        cases = [
            (1, 1, "under", 2.75, 1.96, .96),
            (2, 1, "under", 2.75, 1.96, -.5),
            (2, 1, "over", 2.75, 1.96, .48),
            (2, 1, "under", 3.25, 2, .5),
            (2, 1, "over", 3.25, 2, -.5),
            (1, 0, "under", 2.5, 1.95, .95),
            (2, 2, "under", 3.25, 2, -1),
        ]
        for h, a, side, line, odds, expected in cases:
            with self.subTest(h=h, a=a, side=side, line=line):
                self.assertAlmostEqual(payout(dict(kind="totals", side=side,
                    line=line, odds=odds), h, a), expected, places=12)

    def test_totals_exact_fraction_oracle(self):
        # Independent half-goal stake oracle across integer total outcomes.
        for h in range(8):
            for a in range(8):
                for q in range(1, 33):
                    for side in ("over", "under"):
                        for price in (1.8, 1.96, 2.0, 2.25):
                            threshold = Fraction(q, 4)
                            half_floor = (threshold * 2).__floor__()
                            lower = Fraction(half_floor, 2)
                            upper = lower if threshold == lower else lower + Fraction(1, 2)
                            def leg(t):
                                difference = Fraction(h+a) - t
                                if side == "under":
                                    difference = -difference
                                return (Fraction(str(price))-1 if difference > 0
                                        else -1 if difference < 0 else 0)
                            expected = (leg(lower) + leg(upper)) / 2
                            actual = payout(dict(kind="totals", side=side,
                                line=q/4, odds=price), h, a)
                            self.assertAlmostEqual(actual, float(expected), places=12)


if __name__ == "__main__":
    unittest.main()
