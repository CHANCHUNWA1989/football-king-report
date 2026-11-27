import math
import sys
import unittest
from pathlib import Path
from fractions import Fraction

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asian_ev_research import asian_net, expected_value, PRODUCTION_RECOMMENDATIONS


class ExactQuarterTests(unittest.TestCase):
    def test_near_quarter_rejected(self):
        for value in (math.nextafter(.75, math.inf),
                      math.nextafter(-2.25, -math.inf),
                      1e-10, 1.0000000001):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'LINE_MUST_BE_QUARTER'):
                asian_net(1, value, 2)

    def test_invalid_line_in_distribution(self):
        with self.assertRaisesRegex(ValueError, 'LINE_MUST_BE_QUARTER'):
            expected_value({2: .5, 3: .5}, -2.2500000001, 2)

    def test_totals_over_under_boundary(self):
        for line, goals, over, under in ((2.25, 2, -.5, .5),
                                        (2.5, 2, -1, 1),
                                        (2.75, 3, .5, -.5),
                                        (3.0, 3, 0, 0)):
            self.assertEqual(asian_net(goals, -line, 2), over)
            self.assertEqual(asian_net(-goals, line, 2), under)

    def test_exact_grid_against_fraction_oracle(self):
        for margin in range(-30, 61):
            for q in range(-40, 41):
                legs = (q-1, q+1) if q % 2 else (q, q)
                for odds in (1.5, 2.0, 3.25):
                    values = [Fraction(margin) + Fraction(leg, 4) for leg in legs]
                    want = sum((odds-1 if v > 0 else -1 if v < 0 else 0) for v in values)/2
                    self.assertEqual(asian_net(margin, q/4, odds), want)

    def test_distribution_equals_grade_weighting(self):
        self.assertAlmostEqual(expected_value({1: .2, 2: .3, 3: .5}, -2.25, 1.8), .05)
        self.assertEqual(PRODUCTION_RECOMMENDATIONS, 'DISABLED')
