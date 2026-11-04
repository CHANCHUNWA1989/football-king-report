"""Fail-closed boundaries for hypothetical EV calculations."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asian_ev_arithmetic_243 import calculate


class AsianEVBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.p = {'FULL_WIN': .4, 'HALF_WIN': .1, 'PUSH': .1, 'HALF_LOSS': .2, 'FULL_LOSS': .2}

    def test_only_push_has_zero_ev(self):
        p = {key: 0 for key in self.p}
        p['PUSH'] = 1
        self.assertEqual(calculate(p, 1.95)['hypothetical_ev'], 0)

    def test_half_win_is_half_profit(self):
        p = {key: 0 for key in self.p}
        p['HALF_WIN'] = 1
        self.assertEqual(calculate(p, 1.95)['hypothetical_ev'], .475)

    def test_half_loss_is_half_stake(self):
        p = {key: 0 for key in self.p}
        p['HALF_LOSS'] = 1
        self.assertEqual(calculate(p, 1.95)['hypothetical_ev'], -.5)

    def test_no_automatic_qualification_even_when_ev_positive(self):
        p = {key: 0 for key in self.p}
        p['FULL_WIN'] = 1
        result = calculate(p, 1.95)
        self.assertGreater(result['hypothetical_ev'], .05)
        self.assertEqual(result['status'], 'HOLD')
        self.assertFalse(result['executable_odds_verified'])
        self.assertFalse(result['model_calibrated'])
        self.assertEqual(result['production_recommendations'], 'DISABLED')

    def test_malformed_inputs_rejected(self):
        for value in (float('inf'), -0.1, True, None):
            p = dict(self.p)
            p['FULL_WIN'] = value
            with self.assertRaises(ValueError):
                calculate(p, 1.95)
        with self.assertRaises(ValueError):
            calculate({'FULL_WIN': 1}, 1.95)


if __name__ == '__main__':
    unittest.main()
