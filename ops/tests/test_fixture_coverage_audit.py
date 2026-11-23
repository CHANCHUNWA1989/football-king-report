"""Fixtures are synthetic; never reusable as real bookmaker evidence."""
import unittest
from datetime import datetime
from ops.fixture_coverage_audit import audit

T = '2026-11-23T12:00:00Z'
START = '2026-11-23T12:00:00Z'
END = '2026-11-23T22:00:00Z'
NOW = '2026-11-23T12:02:00Z'


def sources():
    shadow = {'predictions': [{'event_id': 'id-a', 'league': 'epl',
                               'kickoff_utc': '2026-11-23T20:00:00Z',
                               'prediction_utc': '2026-11-23T11:50:00Z'}],
              'model_calibrated': False, 'lineups_confirmed': False, 'xg_verified': False}
    market = {'as_of_utc': T, 'events': [{'source_event_id': 'id-a', 'league': 'epl',
               'home': 'Home', 'away': 'Away',
               'kickoff_utc': '2026-11-23T20:00:00Z',
               'market_last_update_utc': T}]}
    pair = {'status': 'READY_RESEARCH', 'matched_count': 1}
    collection = {'collection_status': 'READY_RESEARCH', 'as_of_utc': T}
    return shadow, market, pair, collection


class FixtureAuditTests(unittest.TestCase):
    def run_audit(self, src=None):
        return audit(*(src or sources()), start=START, end=END, now=NOW)

    def test_fresh_exact_id_remains_hold_without_executable_quote(self):
        report = self.run_audit()
        self.assertEqual(report['window_shadow_predictions'], 1)
        self.assertTrue(report['fixtures'][0]['model_exact_id_candidate_found'])
        self.assertIn('NO_AUTHENTICATED_EXECUTABLE_PRICE', report['fixtures'][0]['blockers'])
        self.assertEqual(report['status'], 'HOLD')
        self.assertEqual(report['production_recommendations'], 'DISABLED')
        self.assertEqual(report['certified_fixtures'], 0)

    def test_stale_quote_and_quota_hold(self):
        s = sources()
        s[1]['as_of_utc'] = '2026-11-20T08:00:00Z'
        s[1]['events'][0]['market_last_update_utc'] = '2026-11-20T07:59:00Z'
        s[3]['collection_status'] = 'HOLD'
        x = self.run_audit(s)['fixtures'][0]['blockers']
        self.assertIn('STALE_OR_INVALID_MARKET_CONSENSUS', x)
        self.assertIn('MARKET_COLLECTION_NOT_READY', x)

    def test_name_match_never_replaces_source_identity(self):
        s = sources()
        s[0]['predictions'][0]['event_id'] = 'other-provider-id'
        self.assertIn('NO_EXACT_SOURCE_ID_FORECAST_BRIDGE', self.run_audit(s)['fixtures'][0]['blockers'])

    def test_late_forecast_rejected(self):
        s = sources()
        s[0]['predictions'][0]['prediction_utc'] = '2026-11-23T20:30:00Z'
        self.assertIn('NO_EXACT_SOURCE_ID_FORECAST_BRIDGE', self.run_audit(s)['fixtures'][0]['blockers'])

    def test_duplicate_event_id_fails_closed(self):
        s = sources()
        s[1]['events'].append(dict(s[1]['events'][0]))
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_MARKET_EVENT_ID'):
            self.run_audit(s)

    def test_global_pair_count_never_attests_this_fixture(self):
        row = self.run_audit()['fixtures'][0]
        self.assertIn('EVENT_PAIR_PROVENANCE_UNATTESTED', row['blockers'])

    def test_quote_after_batch_rejected(self):
        s = sources()
        s[1]['events'][0]['market_last_update_utc'] = '2026-11-23T12:01:00Z'
        self.assertIn('INVALID_QUOTE_CHRONOLOGY', self.run_audit(s)['fixtures'][0]['blockers'])

    def test_quote_after_kickoff_rejected(self):
        s = sources()
        s[1]['events'][0]['market_last_update_utc'] = '2026-11-23T20:01:00Z'
        self.assertIn('INVALID_QUOTE_CHRONOLOGY', self.run_audit(s)['fixtures'][0]['blockers'])

    def test_future_snapshot_is_not_fresh(self):
        s = sources()
        s[1]['as_of_utc'] = '2026-11-23T14:00:00Z'
        self.assertIn('STALE_OR_INVALID_MARKET_CONSENSUS', self.run_audit(s)['fixtures'][0]['blockers'])


    def test_expected_fixture_without_market_still_reported_hold(self):
        src = sources()
        src[1]['events'] = []
        expected = [{'source_event_id': 'id-a', 'league': 'epl', 'home': 'Home',
                     'away': 'Away', 'kickoff_utc': '2026-11-23T20:00:00Z'}]
        report = audit(*src, start=START, end=END, now=NOW, expected_fixtures=expected)
        self.assertEqual(report['window_market_events'], 0)
        self.assertEqual(report['window_expected_fixtures'], 1)
        self.assertEqual(report['missing_expected_market_events'], 1)
        self.assertEqual(len(report['fixtures']), 1)
        self.assertIn('EXPECTED_FIXTURE_MISSING_MARKET_EVENT', report['fixtures'][0]['blockers'])
        self.assertFalse(report['fixtures'][0]['verified_positive_ev'])
        self.assertEqual(report['certified_fixtures'], 0)
        self.assertEqual(report['production_recommendations'], 'DISABLED')
        self.assertFalse(report['expected_fixture_manifest_independently_authenticated'])

    def test_expected_fixture_matching_market_is_not_duplicated(self):
        expected = [{'source_event_id': 'id-a', 'league': 'epl', 'home': 'Home',
                     'away': 'Away', 'kickoff_utc': '2026-11-23T20:00:00Z'}]
        report = audit(*sources(), start=START, end=END, now=NOW, expected_fixtures=expected)
        self.assertEqual(report['window_market_events'], 1)
        self.assertEqual(report['missing_expected_market_events'], 0)
        self.assertEqual(len(report['fixtures']), 1)
        self.assertEqual(report['fixtures'][0]['status'], 'HOLD')

    def test_expected_fixture_identity_conflict_fails_closed(self):
        expected = [{'source_event_id': 'id-a', 'league': 'epl', 'home': 'Different',
                     'away': 'Away', 'kickoff_utc': '2026-11-23T20:00:00Z'}]
        with self.assertRaisesRegex(ValueError, 'EXPECTED_FIXTURE_IDENTITY_CONFLICT'):
            audit(*sources(), start=START, end=END, now=NOW, expected_fixtures=expected)

    def test_duplicate_expected_ids_rejected(self):
        expected = [{'source_event_id': 'id-a', 'league': 'epl', 'home': 'Home',
                     'away': 'Away', 'kickoff_utc': '2026-11-23T20:00:00Z'}] * 2
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_EXPECTED_EVENT_ID'):
            audit(*sources(), start=START, end=END, now=NOW, expected_fixtures=expected)

    def test_out_of_window_expected_fixture_rejected(self):
        expected = [{'source_event_id': 'id-b', 'league': 'epl', 'home': 'Home',
                     'away': 'Away', 'kickoff_utc': '2026-11-24T23:00:00Z'}]
        with self.assertRaisesRegex(ValueError, 'INVALID_EXPECTED_FIXTURE'):
            audit(*sources(), start=START, end=END, now=NOW, expected_fixtures=expected)

    def test_empty_expected_fixture_manifest_does_not_claim_coverage(self):
        report = audit(*sources(), start=START, end=END, now=NOW, expected_fixtures=[])
        self.assertEqual(report['window_expected_fixtures'], 0)
        self.assertFalse(report['expected_fixture_manifest_independently_authenticated'])
        self.assertEqual(report['status'], 'HOLD')


if __name__ == '__main__':
    unittest.main()
