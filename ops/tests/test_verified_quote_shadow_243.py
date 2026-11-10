"""Research-only quote/model matching regression tests."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verified_quote_shadow_243 import shadow_ev


class QuoteShadowTests(unittest.TestCase):
    def setUp(self):
        self.quote = {'event_id': 'event-1', 'market': 'spreads', 'point': .75,
                      'outcome': 'Away', 'decimal_odds': 1.95,
                      'status': 'FRESH_OBSERVATION_NOT_EXECUTABLE',
                      'market_last_update_utc': '2026-10-17T00:00:00Z',
                      'kickoff_utc': '2026-10-17T01:00:00Z'}
        self.model = {'event_id': 'event-1', 'market': 'spreads', 'point': .75,
                      'outcome': 'Away', 'predicted_at_utc': '2026-10-16T23:30:00Z',
                      'probability_source': 'independent_pre_match_model',
                      'grade_probabilities': {'FULL_WIN': .55, 'HALF_WIN': 0,
                                              'PUSH': 0, 'HALF_LOSS': .25,
                                              'FULL_LOSS': .20}}

    def check(self):
        return shadow_ev(self.quote, self.model, captured_utc='2026-10-17T00:00:30Z')

    def test_matched_shadow_ev_still_hold(self):
        result = self.check()
        self.assertAlmostEqual(result['hypothetical_ev'], .1975)
        self.assertEqual(result['status'], 'HOLD')
        self.assertFalse(result['executable_odds_verified'])

    def test_event_and_line_mismatch(self):
        self.model['event_id'] = 'other-event'
        self.assertEqual(self.check()['reason'], 'IDENTITY_OR_MARKET_MISMATCH')
        self.model['event_id'] = 'event-1'
        self.model['point'] = .5
        self.assertEqual(self.check()['reason'], 'IDENTITY_OR_MARKET_MISMATCH')

    def test_stale_and_inplay(self):
        self.quote['market_last_update_utc'] = '2026-10-16T23:40:00Z'
        self.assertEqual(self.check()['reason'], 'STALE_QUOTE')
        self.quote['market_last_update_utc'] = '2026-10-17T00:00:00Z'
        self.quote['kickoff_utc'] = '2026-10-17T00:00:00Z'
        self.assertEqual(self.check()['reason'], 'LOOKAHEAD_OR_INPLAY')

    def test_model_provenance_and_lookahead(self):
        self.model['probability_source'] = 'bookmaker_devig'
        self.assertEqual(self.check()['reason'], 'NO_INDEPENDENT_MODEL_PROVENANCE')
        self.model['probability_source'] = 'independent_pre_match_model'
        self.model['predicted_at_utc'] = '2026-10-17T00:00:15Z'
        self.assertEqual(self.check()['reason'], 'LOOKAHEAD_OR_INPLAY')


if __name__ == '__main__':
    unittest.main()
