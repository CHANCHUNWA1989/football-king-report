"""Replay new endpoint receipts without upgrading historical or result truth.

Fixtures are synthetic.  A v2 controlled endpoint receipt can close the missing
recorded redirect/final-URL link; it cannot authenticate a publisher, kickoff,
independent upstream collection or a regulation-time result.
"""
import copy
import hashlib
import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ops.index_origin_metadata import validate_manifest
from ops import trusted_result_evidence
from ops.ndr_capture_pack import prepare, validate_capture
from ops.ndr_completion_collector import collect as collect_details
from ops.ndr_result_observations import observe
from ops.shadow_external_evidence_collector import SOURCES, collect as collect_index
from ops.tests import test_ndr_capture_pack as capture_fixture
from ops.tests.test_ndr_completion_observations import detail
from ops.tests.test_ndr_result_observations import page, row


NOW = capture_fixture.NOW
V1 = 'football-king-external-raw-evidence-v1'
V2 = 'football-king-external-raw-evidence-v2'
V3 = 'football-king-external-raw-evidence-v3'
BATCH = NOW - timedelta(minutes=5)
REQUESTED = NOW - timedelta(minutes=4)
COMPLETED = NOW - timedelta(minutes=3)


def manifest_v2(*, body=None):
    provider = 'NDR'
    raw = page() if body is None else body
    return {
        'schema': V2, 'captured_utc': BATCH.isoformat(), 'status': 'HOLD',
        'production_recommendations': 'DISABLED', 'independently_verified': False,
        'eligible_for_model_scoring': False,
        'sources': [{
            'provider': 'DFB', 'source_url': SOURCES['DFB'], 'status': 'ERROR',
            'requested_utc': BATCH.isoformat(), 'completed_utc': BATCH.isoformat(),
            'redirect_policy': 'DENY_ALL', 'final_url': None,
            'error_type': 'URLError', 'error_code': 'SOURCE_NETWORK_ERROR',
            'http_status': None,
        }, {
            'provider': provider, 'source_url': SOURCES[provider],
            'status': 'FETCHED_UNVERIFIED', 'requested_utc': REQUESTED.isoformat(),
            'completed_utc': COMPLETED.isoformat(), 'redirect_policy': 'DENY_ALL',
            'final_url': SOURCES[provider], 'raw_file': provider.lower() + '.html',
            'raw_sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
            'http_status': 200, 'content_type': 'text/html',
        }],
    }


def failure_v2(code='SOURCE_TIMEOUT', *, status=None):
    manifest = manifest_v2()
    source = manifest['sources'][1]
    for key in ('raw_file', 'raw_sha256', 'bytes', 'content_type'):
        source.pop(key)
    error_type = 'HTTPError' if code.startswith('HTTP_') else 'TimeoutError'
    source.update(status='ERROR', final_url=None, error_type=error_type,
                  error_code=code, http_status=status)
    return manifest


class IndexOriginManifestTests(unittest.TestCase):
    def assert_invalid(self, manifest, **kwargs):
        with self.assertRaises(ValueError):
            validate_manifest(manifest, now=NOW, **kwargs)

    def test_exact_v2_receipt_is_valid_and_not_mutated(self):
        manifest = manifest_v2()
        original = copy.deepcopy(manifest)
        self.assertIsNone(validate_manifest(manifest, now=NOW, before=NOW))
        self.assertEqual(manifest, original)
        self.assertEqual(manifest['status'], 'HOLD')
        self.assertIs(manifest['independently_verified'], False)

    def test_two_fixed_sources_are_required_in_collector_order(self):
        manifest = manifest_v2()
        self.assertIsNone(validate_manifest(manifest, now=NOW, before=NOW))
        for sources in ([], manifest['sources'][:1], manifest['sources'][1:],
                        list(reversed(manifest['sources']))):
            with self.subTest(providers=[item['provider'] for item in sources]):
                self.assert_invalid(dict(manifest, sources=sources))

    def test_v2_failed_batch_is_valid_without_success_claims(self):
        for manifest in (failure_v2(), failure_v2('HTTP_REDIRECT_REJECTED', status=302)):
            with self.subTest(sources=manifest['sources']):
                self.assertIsNone(validate_manifest(manifest, now=NOW, before=NOW))

    def test_unknown_and_historical_schema_cannot_be_relabelled_by_validator(self):
        for schema in (None, V1, 'football-king-external-raw-evidence-v3', True):
            with self.subTest(schema=schema):
                manifest = manifest_v2()
                manifest['schema'] = schema
                self.assert_invalid(manifest)

    def test_source_and_final_url_require_exact_pinned_https_identity(self):
        alternatives = [
            SOURCES['NDR'].replace('https://', 'http://', 1),
            SOURCES['NDR'].replace('www.ndr.de', 'ndr.de', 1),
            SOURCES['NDR'].replace('www.ndr.de', 'www.ndr.de.evil.test', 1),
            SOURCES['NDR'].replace('www.ndr.de', 'user@www.ndr.de', 1),
            SOURCES['NDR'].replace('%2C', ','),
            SOURCES['NDR'] + '?source=other', SOURCES['NDR'] + '#result',
            SOURCES['DFB'], '', None,
        ]
        for key in ('source_url', 'final_url'):
            for value in alternatives:
                with self.subTest(key=key, value=value):
                    manifest = manifest_v2()
                    manifest['sources'][1][key] = value
                    self.assert_invalid(manifest)

    def test_redirect_policy_must_record_deny_all(self):
        for value in ('FOLLOW', 'DENY', '', None, False):
            with self.subTest(value=value):
                manifest = manifest_v2()
                manifest['sources'][1]['redirect_policy'] = value
                self.assert_invalid(manifest)

    def test_duplicate_unknown_and_excess_provider_receipts_are_refused(self):
        for scenario in ('duplicate', 'unknown', 'too_many'):
            with self.subTest(scenario=scenario):
                manifest = manifest_v2()
                if scenario == 'duplicate':
                    manifest['sources'].append(copy.deepcopy(manifest['sources'][1]))
                elif scenario == 'unknown':
                    manifest['sources'][1]['provider'] = 'Sportschau'
                else:
                    manifest['sources'] *= 3
                self.assert_invalid(manifest)

    def test_success_metadata_uses_strict_types_bounds_and_normalized_html(self):
        attacks = [
            ('http_status', True), ('http_status', 201), ('http_status', '200'),
            ('bytes', True), ('bytes', 0), ('bytes', 3_000_001), ('bytes', 1.0),
            ('raw_file', '../ndr.html'), ('raw_file', 'dfb.html'),
            ('raw_sha256', 'A' * 64), ('raw_sha256', '0' * 63),
            ('content_type', 'application/json'), ('content_type', 'text/plain'),
            ('content_type', 'Text/HTML'), ('content_type', 'text/html; charset=utf-8'),
            ('content_type', ''), ('content_type', None),
        ]
        for key, value in attacks:
            with self.subTest(key=key, value=value):
                manifest = manifest_v2()
                manifest['sources'][1][key] = value
                self.assert_invalid(manifest)
        manifest = manifest_v2()
        manifest['sources'][1]['content_type'] = 'application/xhtml+xml'
        self.assertIsNone(validate_manifest(manifest, now=NOW))

    def test_all_chronology_bounds_are_enforced_without_future_tolerance(self):
        attacks = [
            ('captured_utc', REQUESTED + timedelta(seconds=1)),
            ('requested_utc', BATCH - timedelta(seconds=1)),
            ('completed_utc', REQUESTED - timedelta(seconds=1)),
            ('completed_utc', NOW + timedelta(microseconds=1)),
        ]
        for key, value in attacks:
            with self.subTest(key=key):
                manifest = manifest_v2()
                target = manifest if key == 'captured_utc' else manifest['sources'][1]
                target[key] = value.isoformat()
                self.assert_invalid(manifest)
        self.assert_invalid(manifest_v2(), before=COMPLETED - timedelta(microseconds=1))
        self.assertIsNone(validate_manifest(manifest_v2(), now=NOW, before=COMPLETED))
        manifest = manifest_v2()
        manifest['sources'][0]['completed_utc'] = (REQUESTED + timedelta(seconds=1)).isoformat()
        self.assert_invalid(manifest)

    def test_receipt_times_must_be_explicit_utc_strings(self):
        invalid = [None, True, 0, '2026-10-19', '2026-10-19T07:57:00',
                   '2026-10-19T08:57:00+01:00', '2026-10-19T07:57:00+00:01',
                   '2026-10-19T07:57:00Ztrailing']
        for key in ('captured_utc', 'requested_utc', 'completed_utc'):
            for value in invalid:
                with self.subTest(key=key, value=value):
                    manifest = manifest_v2()
                    target = manifest if key == 'captured_utc' else manifest['sources'][1]
                    target[key] = value
                    self.assert_invalid(manifest)

    def test_top_level_or_source_promotion_flags_and_unknown_fields_are_refused(self):
        for level in ('manifest', 'source'):
            for key, value in [('independently_verified', True),
                               ('eligible_for_model_scoring', True),
                               ('publisher_authenticated', True),
                               ('production_recommendations', 'ENABLED'),
                               ('source_group', 'INDEPENDENT_A')]:
                with self.subTest(level=level, key=key):
                    manifest = manifest_v2()
                    target = manifest if level == 'manifest' else manifest['sources'][1]
                    target[key] = value
                    self.assert_invalid(manifest)

    def test_success_and_error_receipts_have_disjoint_exact_shapes(self):
        attacks = [('error_type', 'TimeoutError'), ('error_code', 'SOURCE_TIMEOUT')]
        for key, value in attacks:
            manifest = manifest_v2()
            manifest['sources'][1][key] = value
            self.assert_invalid(manifest)
        for key, value in [('raw_file', 'ndr.html'), ('bytes', 1),
                           ('raw_sha256', '0' * 64), ('content_type', 'text/html'),
                           ('final_url', SOURCES['NDR'])]:
            manifest = failure_v2()
            manifest['sources'][1][key] = value
            self.assert_invalid(manifest)

    def test_failed_receipt_error_class_code_and_http_status_are_bounded(self):
        attacks = [
            ('error_type', 'ValueError: PRIVATE_SOURCE_DATA'),
            ('error_type', '../TimeoutError'), ('error_type', ''), ('error_type', None),
            ('error_type', 'A' * 65), ('error_code', 'PRIVATE_RESPONSE'),
            ('error_code', ''), ('error_code', None),
            ('http_status', True), ('http_status', '302'),
            ('http_status', 99), ('http_status', 600),
        ]
        for key, value in attacks:
            with self.subTest(key=key, value=value):
                manifest = failure_v2()
                manifest['sources'][1][key] = value
                self.assert_invalid(manifest)

    def test_missing_receipt_keys_and_wrong_container_types_are_refused(self):
        for key in manifest_v2()['sources'][1]:
            with self.subTest(missing=key):
                manifest = manifest_v2()
                manifest['sources'][1].pop(key)
                self.assert_invalid(manifest)
        for value in (None, [], {'sources': {}}, dict(manifest_v2(), sources={}),
                      dict(manifest_v2(), sources=[None])):
            with self.subTest(value=value):
                self.assert_invalid(value)


class IndexOriginReplayTests(unittest.TestCase):
    def test_direct_observer_cli_reads_v2_without_repository_pythonpath(self):
        with tempfile.TemporaryDirectory() as temporary:
            _raw, _summary, index, _completion = self.make_v2_capture(Path(temporary))
            output = Path(temporary) / 'cli-observations.json'
            script = Path(__file__).resolve().parents[1] / 'ndr_result_observations.py'
            result = subprocess.run([sys.executable, '-E', str(script), '--raw-dir', str(index),
                                     '--output', str(output)], cwd=temporary, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_bytes())
            self.assertEqual(report['observation_count'], 1)
            self.assertIs(report['independently_verified'], False)

    def make_v2_capture(self, root, *, unavailable=False, rows=None):
        """Make fresh v2 fixtures before collecting their fresh detail report."""
        index, _old_completion = capture_fixture.NDRCapturePackTests().make(
            root, missing=unavailable, rows=rows)
        manifest = failure_v2() if unavailable else manifest_v2(body=(index / 'ndr.html').read_bytes())
        (index / 'manifest.json').write_bytes(capture_fixture.encode(manifest))
        completion = root / 'completion-v2'
        with patch('ops.ndr_completion_collector.fetch_detail',
                   side_effect=lambda url: (detail(), 200, 'text/html', url)):
            collect_details(index, completion, now=NOW)
        output = root / 'ndr-capture.tar'
        summary = prepare(index, completion, output, now=NOW)
        return output.read_bytes(), summary, index, completion

    def test_real_collector_to_observer_to_pack_replays_endpoint_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index, completion = root / 'index', root / 'completion'
            calls = []

            def getter(url):
                calls.append(url)
                raw = page() if url == SOURCES['NDR'] else b'<html>synthetic DFB metadata</html>'
                return raw, 200, 'text/html; charset=utf-8', url

            manifest = collect_index(index, getter=getter, now=BATCH)
            self.assertEqual(calls, [SOURCES['NDR']])
            self.assertEqual(manifest['schema'], V3)
            self.assertEqual(manifest['sources'][0]['status'], 'SKIPPED_POLICY')
            self.assertEqual([item['provider'] for item in manifest['sources']], ['DFB', 'NDR'])
            self.assertIsNone(validate_manifest(manifest, now=NOW, before=NOW))
            original_manifest = (index / 'manifest.json').read_bytes()
            self.assertEqual(observe(index, now=NOW)['observation_count'], 1)
            with patch('ops.ndr_completion_collector.fetch_detail',
                       side_effect=lambda url: (detail(), 200, 'text/html', url)):
                collect_details(index, completion, now=NOW)
            output = root / 'ndr-capture.tar'
            summary = prepare(index, completion, output, now=NOW)
            self.assertEqual(summary, validate_capture(output.read_bytes(), witness=NOW, now=NOW))
            self.assertIs(summary['index_origin_chain_complete'], True)
            self.assertEqual(summary['index_origin_chain_scope'], 'NDR_INDEX_ONLY')
            self.assertEqual(summary['index_requested_utc'], BATCH.isoformat())
            self.assertEqual(summary['index_completed_utc'], BATCH.isoformat())
            files = capture_fixture.unpack(output.read_bytes())
            self.assertEqual(files['index-manifest.json'], original_manifest)
            self.assertEqual((index / 'manifest.json').read_bytes(), original_manifest)
            self.assertNotIn('dfb.html', files)
            self.assertNotIn('dfb_content_verified', summary)
            self.assertNotIn('publisher_authenticated', summary)
            self.assertNotIn('upstream_independence_verified', summary)
            self.assertIs(summary['independently_verified'], False)
            self.assertIs(summary['eligible_for_model_scoring'], False)

    def test_v2_original_bytes_replay_with_controlled_endpoint_chain_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, summary, index, completion = self.make_v2_capture(Path(tmp))
            original = {str(path): path.read_bytes()
                        for folder in (index, completion) for path in folder.iterdir()}
            self.assertEqual(validate_capture(raw, witness=NOW, now=NOW), summary)
            self.assertEqual(summary['index_origin_schema'], V2)
            self.assertEqual(summary['index_origin_chain_scope'], 'NDR_INDEX_ONLY')
            self.assertIs(summary['index_origin_chain_complete'], True)
            self.assertEqual(summary['index_requested_utc'], REQUESTED.isoformat())
            self.assertEqual(summary['index_completed_utc'], COMPLETED.isoformat())
            self.assertEqual(summary['observation_count'], 1)
            for field in ('independently_verified', 'eligible_for_model_scoring', 'formal_eligible'):
                self.assertIs(summary[field], False)
            self.assertEqual(original, {str(path): path.read_bytes()
                                       for folder in (index, completion) for path in folder.iterdir()})
            files = capture_fixture.unpack(raw)
            self.assertEqual(files['index-manifest.json'], (index / 'manifest.json').read_bytes())

    def test_v2_failure_is_replayed_as_unavailable_not_a_complete_origin_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, summary, _index, _completion = self.make_v2_capture(Path(tmp), unavailable=True)
            self.assertEqual(validate_capture(raw, witness=NOW, now=NOW), summary)
            self.assertEqual(summary['index_origin_schema'], V2)
            self.assertEqual(summary['index_origin_chain_scope'], 'NDR_INDEX_ONLY')
            self.assertIs(summary['index_origin_chain_complete'], False)
            self.assertEqual(summary['index_requested_utc'], REQUESTED.isoformat())
            self.assertEqual(summary['index_completed_utc'], COMPLETED.isoformat())
            self.assertIs(summary['source_available'], False)
            self.assertEqual(summary['observation_count'], 0)
            self.assertNotIn('ndr.html', capture_fixture.unpack(raw))

    def test_v2_endpoint_receipt_does_not_require_or_certify_accepted_score_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, summary, _index, _completion = self.make_v2_capture(Path(tmp), rows=row(score='LIVE'))
            self.assertEqual(validate_capture(raw, witness=NOW, now=NOW), summary)
            self.assertIs(summary['index_origin_chain_complete'], True)
            self.assertEqual(summary['index_observation_count'], 0)
            self.assertEqual(summary['index_rejected_row_count'], 1)
            self.assertEqual(summary['observation_count'], 0)
            self.assertIs(summary['independently_verified'], False)
            self.assertIs(summary['eligible_for_model_scoring'], False)

    def test_historical_v1_is_replayable_without_backfilled_receipt_or_byte_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, summary = capture_fixture.NDRCapturePackTests().capture(Path(tmp))
            original = bytes(raw)
            replay = validate_capture(raw, witness=NOW, now=NOW)
            self.assertEqual(replay, summary)
            self.assertEqual(raw, original)
            self.assertEqual(replay['index_origin_schema'], V1)
            self.assertEqual(replay['index_origin_chain_scope'], 'NDR_INDEX_ONLY')
            self.assertIs(replay['index_origin_chain_complete'], False)
            self.assertIsNone(replay['index_requested_utc'])
            self.assertIsNone(replay['index_completed_utc'])
            stored = json.loads(capture_fixture.unpack(raw)['index-manifest.json'])
            for field in ('requested_utc', 'completed_utc', 'redirect_policy', 'final_url'):
                self.assertNotIn(field, stored['sources'][0])

    def test_v1_cannot_be_upgraded_by_adding_receipt_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, _summary = capture_fixture.NDRCapturePackTests().capture(Path(tmp))
            files = capture_fixture.unpack(raw)
            manifest = json.loads(files['index-manifest.json'])
            for key in ('requested_utc', 'completed_utc', 'redirect_policy', 'final_url'):
                manifest['sources'][0][key] = manifest_v2()['sources'][1][key]
            files['index-manifest.json'] = capture_fixture.encode(manifest)
            with self.assertRaises(ValueError):
                validate_capture(capture_fixture.repack(files), now=NOW)

    def test_v2_original_receipt_tampering_is_rejected_during_real_tar_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, _summary, _index, _completion = self.make_v2_capture(Path(tmp))
            attacks = [('final_url', SOURCES['NDR'] + '?alternate=1'),
                       ('redirect_policy', 'FOLLOW'), ('http_status', True),
                       ('completed_utc', (NOW + timedelta(seconds=1)).isoformat()),
                       ('requested_utc', (BATCH - timedelta(seconds=1)).isoformat()),
                       ('publisher_authenticated', True)]
            for key, value in attacks:
                with self.subTest(key=key):
                    files = capture_fixture.unpack(raw)
                    manifest = json.loads(files['index-manifest.json'])
                    manifest['sources'][1][key] = value
                    files['index-manifest.json'] = capture_fixture.encode(manifest)
                    with self.assertRaises(ValueError):
                        validate_capture(capture_fixture.repack(files), now=NOW)

    def test_index_completion_must_precede_detail_report_even_if_within_now(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, _summary, _index, _completion = self.make_v2_capture(Path(tmp))
            files = capture_fixture.unpack(raw)
            manifest = json.loads(files['index-manifest.json'])
            manifest['sources'][1]['completed_utc'] = (NOW + timedelta(seconds=1)).isoformat()
            files['index-manifest.json'] = capture_fixture.encode(manifest)
            with self.assertRaises(ValueError):
                validate_capture(capture_fixture.repack(files), now=NOW + timedelta(minutes=1))

    def test_v2_observer_consumes_exact_raw_receipt_without_promoting_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            _raw, _summary, index, _completion = self.make_v2_capture(Path(tmp))
            observed = observe(index, now=NOW)
            self.assertIs(observed['source_available'], True)
            self.assertEqual(observed['observation_count'], 1)
            self.assertEqual(observed['status'], 'HOLD')
            self.assertEqual(observed['production_recommendations'], 'DISABLED')
            self.assertIs(observed['eligible_for_model_scoring'], False)
            for observation in observed['observations']:
                self.assertIs(observation['independently_verified'], False)
                self.assertIs(observation['eligible_for_model_scoring'], False)

    def audit_capture(self, root, raw, summary):
        proof = root / 'proof'
        proof.mkdir()
        bundle = b'{"synthetic_test_bundle":true}\n'
        (proof / 'ndr-capture.tar').write_bytes(raw)
        (proof / 'capture.sigstore.json').write_bytes(bundle)
        options = dict(source_sha='1' * 40, workflow_sha='2' * 40,
                       run_id='39133031901', attempt='1', now=NOW)
        capture = {
            'audit_completed': True, 'signature_identity_and_subject_verified': True,
            'capture_content_replayed': True,
            'subject_sha256': {'ndr-capture.tar': hashlib.sha256(raw).hexdigest()},
            'bundle_sha256': hashlib.sha256(bundle).hexdigest(),
            'verified_tlog_utc': NOW.isoformat(), 'capture_summary': copy.deepcopy(summary),
            'source_commit': options['source_sha'], 'workflow_commit': options['workflow_sha'],
            'run_id': options['run_id'], 'run_attempt': '1',
            'status': 'HOLD', 'production_recommendations': 'DISABLED',
            'independently_verified': False, 'eligible_for_model_scoring': False,
        }
        with patch('ops.trusted_result_evidence.capture_provenance.audit', return_value=capture) as fresh:
            report = trusted_result_evidence.audit(proof, **options)
        fresh.assert_called_once_with(proof, **options)
        self.assertEqual((proof / 'ndr-capture.tar').read_bytes(), raw)
        self.assertEqual((proof / 'capture.sigstore.json').read_bytes(), bundle)
        return report

    def test_v2_audit_closes_only_controlled_origin_gap_keeps_result_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw, summary, _index, _completion = self.make_v2_capture(root)
            report = self.audit_capture(root, raw, summary)
            self.assertIs(report['audit_completed'], True)
            self.assertEqual(report['independently_verified_count'], 0)
            self.assertIs(report['eligible_for_model_scoring'], False)
            case = report['cases'][0]
            self.assertEqual(case['index_origin_chain_status'], 'CONTROLLED_ENDPOINT_CAPTURE_REPLAYED')
            self.assertEqual(case['index_origin_chain_scope'], 'NDR_INDEX_ONLY')
            self.assertNotIn('INDEX_ORIGIN_CHAIN_INCOMPLETE', case['blockers'])
            self.assertEqual(case['publisher_identity_status'], 'UNAUTHENTICATED')
            self.assertEqual(case['upstream_independence_status'], 'UNKNOWN')
            self.assertEqual(case['actual_kickoff_status'], 'UNKNOWN')
            self.assertIsNone(case['actual_kickoff_utc'])
            self.assertEqual(case['regulation_result_status'], 'UNVERIFIED')
            self.assertIs(case['independently_verified'], False)
            for blocker in ('ACTUAL_KICKOFF_EVIDENCE_MISSING',
                            'INDEPENDENT_UPSTREAM_COLLECTION_EVIDENCE_MISSING',
                            'REGULATION_RESULT_NOT_INDEPENDENTLY_AUTHENTICATED'):
                self.assertIn(blocker, case['blockers'])

    def test_v1_audit_retains_explicit_origin_gap_despite_fresh_capture_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw, summary = capture_fixture.NDRCapturePackTests().capture(root)
            report = self.audit_capture(root, raw, summary)
            self.assertIs(report['audit_completed'], True)
            self.assertEqual(report['cases'][0]['index_origin_chain_status'],
                             'INCOMPLETE_FINAL_URL_NOT_RECORDED')
            self.assertIn('INDEX_ORIGIN_CHAIN_INCOMPLETE', report['cases'][0]['blockers'])
            self.assertEqual(report['independently_verified_count'], 0)

    def test_v2_error_receipt_keeps_origin_gap_and_empty_cases_after_fresh_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw, summary, _index, _completion = self.make_v2_capture(root, unavailable=True)
            report = self.audit_capture(root, raw, summary)
            self.assertIs(report['audit_completed'], True)
            self.assertEqual(report['index_origin_schema'], V2)
            self.assertEqual(report['index_origin_chain_scope'], 'NDR_INDEX_ONLY')
            self.assertIs(report['index_origin_chain_complete'], False)
            self.assertEqual(report['cases'], [])
            self.assertEqual(report['independently_verified_count'], 0)
            self.assertIn('INDEX_ORIGIN_CHAIN_INCOMPLETE', report['blockers'])
            self.assertIs(report['eligible_for_model_scoring'], False)


if __name__ == '__main__':
    unittest.main()
