"""Safety regression for quote-to-EV research-only bridge."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quote_ev_shadow_243 import evaluate

P = {'FULL_WIN': .55, 'HALF_WIN': 0, 'PUSH': 0, 'HALF_LOSS': .25, 'FULL_LOSS': .20}


def report():
    return {'status': 'RESEARCH_ONLY', 'quotes': [{
        'event_id': 'fixture-1', 'bookmaker': 'sample', 'market': 'spreads',
        'outcome': 'Away', 'point': .75, 'decimal_odds': 1.95,
        'quote_pre_match_at_capture': True,
        'status': 'FRESH_OBSERVATION_NOT_EXECUTABLE'}]}


def check(data=None, **overrides):
    args = {'event_id': 'fixture-1', 'bookmaker': 'sample', 'market': 'spreads',
            'outcome': 'Away', 'point': .75, 'probabilities': P}
    args.update(overrides)
    return evaluate(report() if data is None else data, **args)


class QuoteEVShadowTests(unittest.TestCase):
    def test_matching_quote_calculates_only_hypothetical_ev(self):
        result = check()
        self.assertAlmostEqual(result['hypothetical_ev'], .1975)
        self.assertEqual(result['status'], 'HOLD')
        self.assertFalse(result['executable_odds_verified'])
        self.assertFalse(result['independent_model_verified'])

    def test_identity_mismatches_rejected(self):
        for field, value in [('event_id', 'wrong'), ('bookmaker', 'wrong'),
                             ('market', 'h2h'), ('outcome', 'Home'), ('point', .5)]:
            with self.subTest(field=field):
                self.assertIsNone(check(**{field: value})['hypothetical_ev'])

    def test_inplay_and_duplicate_quotes_rejected(self):
        data = report()
        data['quotes'][0]['quote_pre_match_at_capture'] = False
        self.assertIsNone(check(data)['hypothetical_ev'])
        data = report()
        data['quotes'].append(dict(data['quotes'][0]))
        self.assertIsNone(check(data)['hypothetical_ev'])

    def test_missing_or_invalid_model_rejected(self):
        self.assertIsNone(check(probabilities={'FULL_WIN': 1})['hypothetical_ev'])
        self.assertIsNone(check({'status': 'HOLD', 'quotes': []})['hypothetical_ev'])


if __name__ == '__main__':
    unittest.main()
