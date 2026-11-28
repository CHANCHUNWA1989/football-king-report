import copy
import hashlib
import unittest

from ops.forward_admission_preflight import assess


def fixture():
    raw = b'fixture forecast bytes'
    record = dict(fixture_key='epl|a|b|2026-11-28', forecast_sha256=hashlib.sha256(raw).hexdigest(),
                  league='epl', native_event_id='123', kickoff_utc='2026-11-28T15:00:00Z',
                  witness_utc='2026-11-28T14:00:00Z', results=[
                      dict(publisher='a', upstream='up-a', collection_start_utc='2026-11-28T17:30:00Z', final=True, score=[2, 1]),
                      dict(publisher='b', upstream='up-b', collection_start_utc='2026-11-28T17:30:00Z', final=True, score=[2, 1])])
    return raw, record


class AdmissionPreflightTests(unittest.TestCase):
    def test_never_certifies_even_complete_claims(self):
        raw, record = fixture()
        record['authenticated'] = True
        result = assess(raw, [record])
        self.assertEqual(result['rows'][0]['reasons'], ['INDEPENDENT_VERIFICATION_REQUIRED'])
        self.assertEqual(result['authenticated_samples'], 0)
        self.assertEqual(result['status'], 'HOLD')
        self.assertEqual(result['production_recommendations'], 'DISABLED')
        self.assertIsNone(result['formal_metrics'])

    def test_tamper(self):
        raw, record = fixture()
        self.assertIn('HASH_MISMATCH', assess(raw + b'!', [record])['rows'][0]['reasons'])

    def test_missing_identity(self):
        raw, record = fixture()
        record['native_event_id'] = None
        self.assertIn('IDENTITY_UNVERIFIED', assess(raw, [record])['rows'][0]['reasons'])

    def test_leakage_and_early_result(self):
        raw, record = fixture()
        record['witness_utc'] = record['kickoff_utc']
        record['results'][0]['collection_start_utc'] = '2026-11-28T16:59:59Z'
        reasons = assess(raw, [record])['rows'][0]['reasons']
        self.assertIn('FORECAST_NOT_PRE_KICKOFF', reasons)
        self.assertIn('RESULT_NOT_POST_MATCH', reasons)

    def test_naive_time(self):
        raw, record = fixture()
        record['kickoff_utc'] = '2026-11-28T15:00:00'
        self.assertIn('KICKOFF_UNVERIFIED', assess(raw, [record])['rows'][0]['reasons'])

    def test_shared_upstream_conflict(self):
        raw, record = fixture()
        record['results'][1].update(upstream='up-a', score=[1, 1])
        reasons = assess(raw, [record])['rows'][0]['reasons']
        self.assertIn('SOURCE_INDEPENDENCE_UNVERIFIED', reasons)
        self.assertIn('SCORE_CONFLICT', reasons)

    def test_duplicate_both_rejected(self):
        raw, record = fixture()
        self.assertTrue(all('DUPLICATE_FIXTURE' in row['reasons'] for row in assess(raw, [record, copy.deepcopy(record)])['rows']))

    def test_invalid_score_and_final(self):
        raw, record = fixture()
        record['results'][0].update(final=1, score=[True, -1])
        self.assertIn('RESULT_NOT_FINAL', assess(raw, [record])['rows'][0]['reasons'])

    def test_invalid_row_and_empty(self):
        self.assertIn('INVALID_ROW', assess(b'', [None])['rows'][0]['reasons'])
        self.assertEqual(assess(b'', [])['candidate_count'], 0)


if __name__ == '__main__':
    unittest.main()
