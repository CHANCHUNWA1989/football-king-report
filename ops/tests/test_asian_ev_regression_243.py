"""Regression checks for hypothetical Asian handicap +0.75 research."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asian_handicap_research import grade


class AsianEVRegression243(unittest.TestCase):
    def test_away_plus_three_quarters(self):
        self.assertEqual(grade(0, 1, 'AWAY', .75), 'FULL_WIN')
        self.assertEqual(grade(1, 1, 'AWAY', .75), 'FULL_WIN')
        self.assertEqual(grade(1, 0, 'AWAY', .75), 'HALF_LOSS')
        self.assertEqual(grade(2, 0, 'AWAY', .75), 'FULL_LOSS')

    def test_hypothetical_ev_math(self):
        p_not_lose, p_lose_one, p_lose_two_plus = .55, .25, .20
        ev = .95 * p_not_lose - .5 * p_lose_one - p_lose_two_plus
        self.assertAlmostEqual(ev, .1975)

    def test_invalid_line_rejected(self):
        with self.assertRaises(ValueError):
            grade(1, 0, 'AWAY', .7)


if __name__ == '__main__':
    unittest.main()
