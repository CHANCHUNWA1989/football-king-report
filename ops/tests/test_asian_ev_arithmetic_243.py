"""Offline-only tests for Asian handicap EV arithmetic."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asian_ev_arithmetic_243 import calculate


class AsianEVArithmeticTests(unittest.TestCase):
    def test_away_plus_075_scenario(self):
        p = {'FULL_WIN': .55, 'HALF_WIN': 0, 'PUSH': 0, 'HALF_LOSS': .25, 'FULL_LOSS': .20}
        out = calculate(p, 1.95)
        self.assertAlmostEqual(out['hypothetical_ev'], .1975)
        self.assertEqual(out['status'], 'HOLD')
        self.assertEqual(out['production_recommendations'], 'DISABLED')
        self.assertFalse(out['executable_odds_verified'])

    def test_half_win_and_push(self):
        p = {'FULL_WIN': 0, 'HALF_WIN': .4, 'PUSH': .3, 'HALF_LOSS': .2, 'FULL_LOSS': .1}
        self.assertAlmostEqual(calculate(p, 2.0)['hypothetical_ev'], 0.0)

    def test_invalid_inputs_rejected(self):
        p = {'FULL_WIN': .55, 'HALF_WIN': 0, 'PUSH': 0, 'HALF_LOSS': .25, 'FULL_LOSS': .20}
        for price in (True, float('nan'), 1.0):
            with self.assertRaises(ValueError):
                calculate(p, price)
        p['FULL_WIN'] = .9
        with self.assertRaises(ValueError):
            calculate(p, 1.95)


if __name__ == '__main__':
    unittest.main()
