"""DFB's collection boundary is enforced before any network dependency runs."""
from datetime import datetime, timezone
import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from ops import shadow_external_evidence_collector as collector
from ops.index_origin_metadata import validate_manifest
from ops.ndr_capture_pack import prepare, validate_capture
from ops.ndr_completion_collector import collect as collect_details
from ops.ndr_result_observations import observe
from ops.tests.test_ndr_completion_observations import detail
from ops.tests.test_ndr_result_observations import page
from ops.tests.test_index_origin_evidence import manifest_v2, failure_v2
from ops.tests.test_ndr_capture_pack import encode, unpack, repack


NOW = datetime(2026, 10, 21, 19, tzinfo=timezone.utc)
DFB = collector.SOURCES['DFB']
NDR = collector.SOURCES['NDR']
REASON = 'DFB_AUTOMATED_COLLECTION_AND_PUBLIC_RAW_REUSE_NOT_AUTHORIZED'


class DFBSourcePolicyTests(unittest.TestCase):
    def collect(self, folder, *, failure=None):
        getter = Mock(side_effect=failure or (lambda url: (page(), 200, 'text/html', url)))
        report = collector.collect(folder, getter=getter, now=NOW)
        getter.assert_called_once_with(NDR)
        return report

    def test_collector_skips_dfb_before_injected_getter_and_fetches_only_ndr(self):
        getter = Mock(side_effect=lambda url: (b'<html>NDR</html>', 200, 'text/html', url))
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'raw'
            report = collector.collect(folder, getter=getter, now=NOW)
            self.assertEqual(getter.call_args_list, [unittest.mock.call(NDR)])
            self.assertEqual(report['sources'][0]['status'], 'SKIPPED_POLICY')
            self.assertFalse((folder / 'dfb.html').exists())

    def test_direct_dfb_fetch_rejects_before_injected_or_default_opener(self):
        for injected in (False, True):
            with self.subTest(injected=injected), patch.object(collector, 'build_opener') as builder:
                opener = Mock(side_effect=AssertionError('DFB network dependency was reached'))
                builder.return_value.open = opener
                with self.assertRaisesRegex(ValueError, REASON):
                    collector.fetch(DFB, **({'opener': opener} if injected else {}))
                opener.assert_not_called()
                builder.assert_not_called()

    def test_skip_has_exact_policy_shape_with_no_fabricated_request_or_raw_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'raw'
            report = self.collect(folder)
            self.assertEqual(report['schema'], 'football-king-external-raw-evidence-v3')
            self.assertEqual(report['sources'][0], {
                'provider': 'DFB', 'source_url': DFB, 'status': 'SKIPPED_POLICY',
                'policy_reason': REASON, 'terms_reference': 'https://www.dfb.de/nutzungsbedingungen',
                'requested_utc': None, 'completed_utc': None, 'redirect_policy': None,
                'final_url': None, 'http_status': None,
            })
            self.assertEqual(sorted(path.name for path in folder.iterdir()), ['manifest.json', 'ndr.html'])
            validate_manifest(report, now=NOW)
            self.assertEqual(json.loads((folder / 'manifest.json').read_bytes()), report)

    def test_environment_has_no_permission_or_legacy_schema_bypass(self):
        with patch.dict(os.environ, {
            'ALLOW_DFB_FETCH': '1', 'DFB_COLLECTION_AUTHORIZED': 'true',
            'DFB_PUBLIC_RAW_REUSE_AUTHORIZED': 'true', 'EXTERNAL_EVIDENCE_SCHEMA': 'v2',
        }), tempfile.TemporaryDirectory() as temporary:
            report = self.collect(Path(temporary) / 'raw')
            self.assertEqual(report['schema'], 'football-king-external-raw-evidence-v3')
            self.assertEqual(report['sources'][0]['status'], 'SKIPPED_POLICY')
            opener = Mock()
            with self.assertRaisesRegex(ValueError, REASON):
                collector.fetch(DFB, opener=opener)
            opener.assert_not_called()

    def test_no_caller_permission_or_schema_argument_exists(self):
        for argument in ('allow_dfb', 'authorized', 'policy_override', 'schema'):
            with self.subTest(argument=argument), tempfile.TemporaryDirectory() as temporary:
                getter = Mock()
                with self.assertRaises(TypeError):
                    collector.collect(Path(temporary) / 'raw', getter=getter, **{argument: True})
                getter.assert_not_called()

    def test_skip_receipt_rejects_each_missing_extra_forged_or_non_null_field(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = self.collect(Path(temporary) / 'raw')
        attacks = [('requested_utc', NOW.isoformat()), ('completed_utc', NOW.isoformat()),
                   ('redirect_policy', 'DENY_ALL'), ('final_url', DFB), ('http_status', 200),
                   ('http_status', False), ('status', 'ERROR'), ('status', 'FETCHED_UNVERIFIED'),
                   ('policy_reason', 'AUTHORIZED'), ('terms_reference', 'https://example.org/'),
                   ('source_url', NDR), ('raw_file', 'dfb.html'), ('bytes', 0),
                   ('raw_sha256', '0' * 64), ('content_type', 'text/html'),
                   ('error_type', 'SourcePolicyError'), ('error_code', 'SOURCE_ERROR'),
                   ('independently_verified', True), ('eligible_for_model_scoring', True),
                   ('publisher_authenticated', True)]
        for key, value in attacks:
            with self.subTest(key=key, value=value):
                bad = copy.deepcopy(report)
                bad['sources'][0][key] = value
                with self.assertRaises(ValueError):
                    validate_manifest(bad, now=NOW)
        for key in report['sources'][0]:
            with self.subTest(missing=key):
                bad = copy.deepcopy(report)
                del bad['sources'][0][key]
                with self.assertRaises(ValueError):
                    validate_manifest(bad, now=NOW)

    def test_v3_requires_ndr_attempt_and_original_provider_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = self.collect(Path(temporary) / 'raw')
        for sources in [report['sources'][:1], report['sources'][1:], list(reversed(report['sources'])),
                        [report['sources'][0]] * 2, report['sources'] * 2]:
            with self.subTest(sources=sources), self.assertRaises(ValueError):
                validate_manifest(dict(report, sources=sources), now=NOW)
        bad = copy.deepcopy(report)
        bad['sources'][1] = dict(bad['sources'][0], provider='NDR', source_url=NDR)
        with self.assertRaises(ValueError):
            validate_manifest(bad, now=NOW)

    def test_v2_and_v3_cannot_relabel_each_others_dfb_receipts(self):
        # Historical exact v2 ERROR and FETCHED receipts remain interpretable.
        old = manifest_v2()
        validate_manifest(old, now=NOW)
        fetched = copy.deepcopy(old['sources'][1])
        fetched.update(provider='DFB', source_url=DFB, final_url=DFB, raw_file='dfb.html')
        old['sources'][0] = fetched
        old['sources'][0]['requested_utc'] = old['captured_utc']
        old['sources'][0]['completed_utc'] = old['captured_utc']
        validate_manifest(old, now=NOW)
        for historical in (old, manifest_v2(), failure_v2()):
            with self.subTest(historical=historical):
                with self.assertRaises(ValueError):
                    validate_manifest(dict(historical, schema='football-king-external-raw-evidence-v3'), now=NOW)
        with tempfile.TemporaryDirectory() as temporary:
            current = self.collect(Path(temporary) / 'raw')
        with self.assertRaises(ValueError):
            validate_manifest(dict(current, schema='football-king-external-raw-evidence-v2'), now=NOW)

    def test_ndr_failure_keeps_policy_skip_and_has_only_one_real_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'raw'
            report = self.collect(folder, failure=TimeoutError('private message'))
            self.assertEqual([item['status'] for item in report['sources']], ['SKIPPED_POLICY', 'ERROR'])
            self.assertEqual(report['sources'][1]['error_code'], 'SOURCE_TIMEOUT')
            self.assertEqual(sorted(path.name for path in folder.iterdir()), ['manifest.json'])
            validate_manifest(report, now=NOW)
            observed = observe(folder, now=NOW)
            self.assertFalse(observed['source_available'])
            self.assertEqual(observed['observation_count'], 0)

    def test_v3_observer_cli_reads_policy_skip_without_repository_pythonpath(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            index = root / 'index'
            self.collect(index)
            output = root / 'observations.json'
            script = Path(__file__).resolve().parents[1] / 'ndr_result_observations.py'
            result = subprocess.run([sys.executable, '-E', str(script), '--raw-dir', str(index),
                                     '--output', str(output)], cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            observed = json.loads(output.read_bytes())
            self.assertEqual(observed['source']['index_manifest_schema'],
                             'football-king-external-raw-evidence-v3')
            self.assertEqual(observed['observation_count'], 1)
            self.assertIs(observed['independently_verified'], False)

    def make_capture(self, root, *, failure=None):
        index, completion = root / 'index', root / 'completion'
        self.collect(index, failure=failure)
        getter = Mock(side_effect=lambda url: (detail(), 200, 'text/html', url))
        with patch('ops.ndr_completion_collector.fetch_detail', getter):
            report = collect_details(index, completion, now=NOW)
        if failure:
            getter.assert_not_called()
        else:
            self.assertEqual(getter.call_count, 1)
        output = root / 'ndr-capture.tar'
        summary = prepare(index, completion, output, now=NOW)
        return output.read_bytes(), summary, index, completion, report

    def test_v3_observer_and_pack_preserve_skip_and_ndr_endpoint_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            raw, summary, index, _completion, report = self.make_capture(Path(temporary))
            self.assertEqual(summary, validate_capture(raw, witness=NOW, now=NOW))
            self.assertEqual(summary['index_origin_schema'], 'football-king-external-raw-evidence-v3')
            self.assertTrue(summary['index_origin_chain_complete'])
            self.assertEqual(summary['index_requested_utc'], NOW.isoformat())
            self.assertEqual(summary['capture_latest_utc'], NOW.isoformat())
            self.assertEqual(summary['observation_count'], 1)
            self.assertEqual(report['requests_attempted'], 1)
            self.assertFalse(summary['independently_verified'])
            self.assertFalse(summary['eligible_for_model_scoring'])
            files = unpack(raw)
            self.assertEqual(files['index-manifest.json'], (index / 'manifest.json').read_bytes())
            self.assertNotIn('dfb.html', files)
            self.assertEqual(json.loads(files['index-manifest.json'])['sources'][0]['status'], 'SKIPPED_POLICY')

    def test_v3_ndr_failure_replays_no_detail_or_result_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            raw, summary, _index, _completion, report = self.make_capture(
                Path(temporary), failure=TimeoutError())
            self.assertEqual(summary, validate_capture(raw, witness=NOW, now=NOW))
            self.assertFalse(summary['index_origin_chain_complete'])
            self.assertEqual(summary['requests_attempted'], 0)
            self.assertEqual(report['observations'], [])
            self.assertNotIn('ndr.html', unpack(raw))

    def test_v3_skip_cannot_hide_dfb_bytes_in_directory_or_tar(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw, _summary, index, completion, _report = self.make_capture(root)
            (index / 'dfb.html').write_bytes(b'not allowed in a new policy capture')
            with self.assertRaisesRegex(ValueError, 'UNLISTED_POLICY_INDEX_RAW_BYTES'):
                observe(index, now=NOW)
            with self.assertRaisesRegex(ValueError, 'UNLISTED_POLICY_INDEX_RAW_BYTES'):
                prepare(index, completion, root / 'second' / 'ndr-capture.tar', now=NOW)
            files = unpack(raw)
            files['dfb.html'] = b'smuggled'
            with self.assertRaises(ValueError):
                validate_capture(repack(files), witness=NOW, now=NOW)

    def test_v3_pack_rejects_fetched_dfb_relabelled_old_receipt_or_promotion_claim(self):
        with tempfile.TemporaryDirectory() as temporary:
            raw, _summary, _index, _completion, _report = self.make_capture(Path(temporary))
        attacks = [manifest_v2()['sources'][0], dict(manifest_v2()['sources'][1],
                   provider='DFB', source_url=DFB, final_url=DFB, raw_file='dfb.html')]
        for attack in attacks:
            files = unpack(raw)
            manifest = json.loads(files['index-manifest.json'])
            manifest['sources'][0] = attack
            files['index-manifest.json'] = encode(manifest)
            with self.assertRaises(ValueError):
                validate_capture(repack(files), witness=NOW, now=NOW)
        files = unpack(raw)
        manifest = json.loads(files['index-manifest.json'])
        manifest['sources'][0]['independently_verified'] = True
        files['index-manifest.json'] = encode(manifest)
        with self.assertRaises(ValueError):
            validate_capture(repack(files), witness=NOW, now=NOW)


if __name__ == '__main__':
    unittest.main()
