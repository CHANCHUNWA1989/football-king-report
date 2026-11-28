import copy
import hashlib
import json
import unittest

from ops.forward_evidence_pipeline import audit_pipeline


def fixture():
    row = dict(league='epl', event_id='archive-1', home='A', away='B',
               kickoff_utc='2026-11-28T15:00:00Z', prediction_utc='2026-11-28T14:00:00Z')
    raw = json.dumps(dict(predictions=[row], predictions_count=1)).encode()
    digest = hashlib.sha256(raw).hexdigest()
    evidence = dict(native_event_id='provider-1', actual_kickoff_utc=row['kickoff_utc'],
                    witness_utc='2026-11-28T14:30:00Z', results=[])
    for publisher in ('one', 'two'):
        evidence['results'].append(dict(publisher=publisher, upstream=publisher, native_event_id='native-'+publisher,
            league='epl', home='A', away='B', kickoff_utc=row['kickoff_utc'],
            collection_start_utc='2026-11-28T17:30:00Z', final=True, score=[2, 1]))
    return raw, digest, dict(identity=row, evidence=evidence)


class EvidencePipelineTests(unittest.TestCase):
    def test_clean_claims_still_not_certified(self):
        raw, digest, claim = fixture()
        result = audit_pipeline(raw, digest, [claim])
        self.assertEqual(result['rows'][0]['reasons'], ['INDEPENDENT_VERIFICATION_REQUIRED'])
        self.assertEqual(result['bound_count'], 1)
        self.assertEqual(result['authenticated_samples'], 0)
        self.assertIsNone(result['formal_metrics'])
        self.assertEqual(result['status'], 'HOLD')
        self.assertEqual(result['production_recommendations'], 'DISABLED')

    def test_unbound_identity_never_uses_evidence(self):
        raw, digest, claim = fixture()
        claim['identity']['home'] = 'X'
        self.assertEqual(audit_pipeline(raw, digest, [claim])['rows'][0]['reasons'], ['NO_EXACT_ARCHIVED_ROW'])

    def test_digest_mismatch(self):
        raw, digest, claim = fixture()
        self.assertEqual(audit_pipeline(raw+b' ', digest, [claim])['rows'][0]['reasons'], ['ARCHIVE_DIGEST_MISMATCH'])

    def test_duplicate_claim(self):
        raw, digest, claim = fixture()
        result = audit_pipeline(raw, digest, [claim, copy.deepcopy(claim)])
        self.assertEqual(result['bound_count'], 0)
        self.assertTrue(all(x['reasons']==['DUPLICATE_CLAIM'] for x in result['rows']))

    def test_recorded_kickoff_not_actual_kickoff(self):
        raw, digest, claim = fixture()
        del claim['evidence']['actual_kickoff_utc']
        self.assertIn('KICKOFF_UNVERIFIED', audit_pipeline(raw, digest, [claim])['rows'][0]['reasons'])

    def test_witness_after_recorded_kickoff(self):
        raw, digest, claim = fixture()
        claim['evidence'].update(actual_kickoff_utc='2026-11-28T16:00:00Z', witness_utc='2026-11-28T15:30:00Z')
        self.assertIn('WITNESS_OUTSIDE_ARCHIVED_WINDOW', audit_pipeline(raw, digest, [claim])['rows'][0]['reasons'])

    def test_witness_before_forecast(self):
        raw, digest, claim = fixture()
        claim['evidence']['witness_utc']='2026-11-28T13:59:00Z'
        self.assertIn('WITNESS_OUTSIDE_ARCHIVED_WINDOW', audit_pipeline(raw, digest, [claim])['rows'][0]['reasons'])

    def test_result_borrowed_from_other_fixture(self):
        raw, digest, claim = fixture()
        claim['evidence']['results'][0]['away']='C'
        self.assertIn('RESULT_IDENTITY_MISMATCH', audit_pipeline(raw, digest, [claim])['rows'][0]['reasons'])

    def test_missing_provider_native_id(self):
        raw, digest, claim = fixture()
        del claim['evidence']['results'][0]['native_event_id']
        self.assertIn('RESULT_IDENTITY_MISMATCH', audit_pipeline(raw, digest, [claim])['rows'][0]['reasons'])

    def test_shared_upstream_and_score_conflict(self):
        raw, digest, claim = fixture()
        claim['evidence']['results'][1].update(upstream='one', score=[0, 0])
        reasons=audit_pipeline(raw, digest, [claim])['rows'][0]['reasons']
        self.assertIn('SOURCE_INDEPENDENCE_UNVERIFIED', reasons)
        self.assertIn('SCORE_CONFLICT', reasons)

    def test_missing_evidence_and_claimed_approval(self):
        raw, digest, claim = fixture()
        claim['evidence']={'authenticated': True, 'native_event_id': 'archive-1'}
        result=audit_pipeline(raw, digest, [claim])
        self.assertEqual(result['authenticated_samples'], 0)
        self.assertIn('KICKOFF_UNVERIFIED', result['rows'][0]['reasons'])

    def test_invalid_nested_claim(self):
        raw, digest, claim = fixture()
        result=audit_pipeline(raw, digest, [None, {'identity': None}, claim])
        self.assertEqual(result['candidate_count'], 3)
        self.assertEqual(result['bound_count'], 1)
        self.assertEqual(result['rows'][0]['reasons'], ['INVALID_CLAIM'])

    def two_fixtures(self):
        _, _, first = fixture()
        second = copy.deepcopy(first)
        second['identity'].update(event_id='archive-2', away='C')
        for result in second['evidence']['results']:
            result['away'] = 'C'
        raw = json.dumps(dict(predictions=[first['identity'], second['identity']],
                              predictions_count=2)).encode()
        return raw, hashlib.sha256(raw).hexdigest(), first, second

    def test_native_result_id_reuse_across_fixtures(self):
        raw, digest, first, second = self.two_fixtures()
        result = audit_pipeline(raw, digest, [first, second])
        self.assertEqual(result['bound_count'], 2)
        self.assertTrue(all('RESULT_NATIVE_ID_REUSED_ACROSS_FIXTURES' in
                            row['reasons'] for row in result['rows']))
        self.assertEqual(result['authenticated_samples'], 0)

    def test_upstream_collision_even_if_publisher_label_changes(self):
        raw, digest, first, second = self.two_fixtures()
        for r in second['evidence']['results']:
            r['publisher'] += '-alias'
            r['upstream'] = r['upstream'].upper()
        result = audit_pipeline(raw, digest, [first, second])
        self.assertTrue(all('RESULT_NATIVE_ID_REUSED_ACROSS_FIXTURES' in
                            row['reasons'] for row in result['rows']))

    def test_distinct_namespaces_are_not_native_id_conflicts(self):
        raw, digest, first, second = self.two_fixtures()
        for r in second['evidence']['results']:
            r['publisher'] += '-other'
            r['upstream'] += '-other'
        result = audit_pipeline(raw, digest, [first, second])
        self.assertTrue(all(row['reasons'] == ['INDEPENDENT_VERIFICATION_REQUIRED']
                            for row in result['rows']))
        self.assertEqual(result['authenticated_samples'], 0)

    def test_claim_limit_before_reading_claim_rows(self):
        from unittest.mock import patch
        raw, digest, claim = fixture()
        with patch('ops.forward_evidence_pipeline.MAX_ROWS', 1):
            with self.assertRaisesRegex(ValueError, 'bounded list'):
                audit_pipeline(raw, digest, [claim, claim])

if __name__ == '__main__':
    unittest.main()
