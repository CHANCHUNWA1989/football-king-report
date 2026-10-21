"""Bounded NDR detail collection is separate from authenticated result scoring."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from ops.ndr_completion_collector import collect, fetch_detail, MAX_BYTES, _NoRedirects
from ops.tests.test_ndr_result_observations import page, row
from ops.ndr_result_observations import SOURCE_URL
from ops.ndr_completion_observations import NEW_POLICY

NOW = datetime(2026, 10, 19, tzinfo=timezone.utc)
DETAIL_URL = 'https://www.ndr.de/sport/ergebnisse/spielstatistik-5884.html'
DETAIL = b'<html><body>bounded detail bytes</body></html>'


class Response:
    def __init__(self, body=DETAIL, url=DETAIL_URL, status=200, content_type='text/html; charset=utf-8'):
        self.body, self.url, self.status = body, url, status
        self.headers = {'Content-Type': content_type}
        self.read_sizes = []

    def read(self, size):
        self.read_sizes.append(size)
        return self.body[:size]

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class NDRCompletionCollectorTests(unittest.TestCase):
    def test_stable_seven_fixture_cohort_rotates_across_three_utc_days(self):
        rows = ''.join(row(fixture=str(5884 + i), home=str(264 + i), away=str(110 + i),
                           date=f'{16 + i:02d}.10.') for i in range(7))
        batches = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_source(root / 'raw', rows)
            for day in range(3):
                with patch('ops.ndr_completion_collector.fetch_detail',
                           side_effect=lambda url: (DETAIL, 200, 'text/html', url)) as fetch, \
                        patch('ops.ndr_completion_collector.parse_detail', side_effect=self.candidate):
                    got = collect(root / 'raw', root / f'out-{day}', now=NOW + timedelta(days=day))
                self.assertEqual(fetch.call_count, 3)
                batches.append({item['provider_fixture_id'] for item in got['sources']})
            self.assertEqual(len(set.union(*batches)), 7,
                             'Stable cohort is stuck on the same first three fixtures')

    def test_configured_limits_are_recorded_in_new_selection_metadata(self):
        rows = ''.join(row(fixture=str(5884 + i), home=str(264 + i), away=str(110 + i),
                           date=f'{16 + i:02d}.10.') for i in range(5))
        for limit in [1, 2]:
            with self.subTest(limit=limit), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.make_source(root / 'raw', rows)
                with patch('ops.ndr_completion_collector.fetch_detail',
                           side_effect=lambda url: (DETAIL, 200, 'text/html', url)), \
                        patch('ops.ndr_completion_collector.parse_detail', side_effect=self.candidate):
                    got = collect(root / 'raw', root / 'out', limit=limit, now=NOW)
                self.assertEqual(got['schema'], 'football-king-ndr-completion-observations-v3')
                self.assertEqual(got['parser_policy'], NEW_POLICY)
                self.assertEqual(got['selection']['request_limit'], limit)
                self.assertEqual(got['selection']['selected_fixture_ids'],
                                 [item['provider_fixture_id'] for item in got['sources']])
                manifest = json.loads((root / 'out' / 'manifest.json').read_text())
                self.assertEqual(manifest['schema'], 'football-king-ndr-completion-raw-evidence-v3')
                self.assertEqual(manifest['parser_policy'], NEW_POLICY)
                self.assertEqual(manifest['selection'], got['selection'])

    def test_fetch_failures_do_not_select_replacements_or_advance_same_day(self):
        rows = ''.join(row(fixture=str(5884 + i), home=str(264 + i), away=str(110 + i),
                           date=f'{16 + i:02d}.10.') for i in range(7))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_source(root / 'raw', rows)
            with patch('ops.ndr_completion_collector.fetch_detail',
                       side_effect=URLError('DO_NOT_LEAK')) as fetch:
                failed = collect(root / 'raw', root / 'failed', now=NOW)
            self.assertEqual(fetch.call_count, 3)
            self.assertEqual(failed['requests_attempted'], 3)
            self.assertEqual(len(failed['fetch_errors']), 3)
            self.assertEqual(failed['observations'], [])
            self.assertEqual(failed['selection']['selected_fixture_ids'],
                             [item['provider_fixture_id'] for item in failed['sources']])
            with patch('ops.ndr_completion_collector.fetch_detail',
                       side_effect=lambda url: (DETAIL, 200, 'text/html', url)), \
                    patch('ops.ndr_completion_collector.parse_detail', side_effect=self.candidate):
                retry = collect(root / 'raw', root / 'retry', now=NOW + timedelta(hours=23))
            self.assertEqual(failed['selection'], retry['selection'])
            self.assertEqual([item['provider_fixture_id'] for item in failed['sources']],
                             [item['provider_fixture_id'] for item in retry['sources']])
            self.assertFalse(failed['independently_verified'])
            self.assertFalse(retry['eligible_for_model_scoring'])

    def make_source(self, folder, rows=None):
        folder.mkdir()
        body = page(rows)
        (folder / 'ndr.html').write_bytes(body)
        manifest = {
            'schema': 'football-king-external-raw-evidence-v1',
            'captured_utc': '2026-10-18T17:56:00+00:00', 'status': 'HOLD',
            'production_recommendations': 'DISABLED', 'independently_verified': False,
            'eligible_for_model_scoring': False,
            'sources': [{'provider': 'NDR', 'source_url': SOURCE_URL,
                         'status': 'FETCHED_UNVERIFIED', 'raw_file': 'ndr.html',
                         'raw_sha256': hashlib.sha256(body).hexdigest(),
                         'bytes': len(body), 'http_status': 200}]}
        (folder / 'manifest.json').write_text(json.dumps(manifest))
        return manifest

    def candidate(self, raw, item, *, policy=NEW_POLICY):
        self.assertEqual(policy, NEW_POLICY)
        return dict(item, parser_policy=policy, completion_display_observed=True,
                    observed_completion_display='beendet',
                    completion_authenticated=False, period_authenticated=False,
                    status='HOLD', production_recommendations='DISABLED',
                    completion_status_unverified=False, result_period_unverified=True,
                    independently_verified=False, eligible_for_model_scoring=False)

    def test_source_bytes_reparsed_and_raw_hashes_preserved_without_scoring(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_source(root / 'raw')
            response = Response()
            opener = Mock()
            opener.open.return_value = response
            with patch('ops.ndr_completion_collector.build_opener', return_value=opener), \
                    patch('ops.ndr_completion_collector.parse_detail', side_effect=self.candidate) as parser:
                got = collect(root / 'raw', root / 'out', now=NOW)
            self.assertEqual(got['attempt_count'], 1)
            self.assertEqual(got['observation_count'], 1)
            self.assertEqual(got['status'], 'HOLD')
            self.assertEqual(got['production_recommendations'], 'DISABLED')
            self.assertFalse(got['independently_verified'])
            self.assertFalse(got['eligible_for_model_scoring'])
            self.assertFalse(got['observations'][0]['eligible_for_model_scoring'])
            self.assertEqual(parser.call_args.args[0], DETAIL)
            self.assertEqual(parser.call_args.args[1]['provider_fixture_id'], '5884')
            source = got['sources'][0]
            self.assertEqual(source['source_url'], DETAIL_URL)
            self.assertEqual(source['final_url'], DETAIL_URL)
            self.assertEqual(source['captured_utc'], NOW.isoformat())
            self.assertEqual(source['http_status'], 200)
            self.assertEqual(source['raw_sha256'], hashlib.sha256(DETAIL).hexdigest())
            self.assertEqual((root / 'out' / source['raw_file']).read_bytes(), DETAIL)
            self.assertEqual(json.loads((root / 'out' / 'manifest.json').read_text())['sources'], got['sources'])
            self.assertEqual(json.loads((root / 'out' / 'report.json').read_text()), got)
            self.assertEqual(response.read_sizes, [MAX_BYTES + 1])
            self.assertEqual(opener.open.call_args.kwargs['timeout'], 15)

    def test_real_detail_parser_accepts_same_fixture_and_quarantines_conflicting_display(self):
        from ops.tests.test_ndr_completion_observations import detail
        for conflict in [False, True]:
            with self.subTest(conflict=conflict), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.make_source(root / 'raw')
                body = detail().replace(b'finalresult">1:0', b'finalresult">2:0') if conflict else detail()
                opener = Mock()
                opener.open.return_value = Response(body=body)
                with patch('ops.ndr_completion_collector.build_opener', return_value=opener):
                    got = collect(root / 'raw', root / 'out', now=NOW)
                self.assertEqual(got['observation_count'], 0 if conflict else 1)
                self.assertEqual(len(got['rejections']), 1 if conflict else 0)
                self.assertEqual(got['requests_attempted'], 1)
                self.assertEqual((root / 'out' / got['sources'][0]['raw_file']).read_bytes(), body)
                if not conflict:
                    self.assertTrue(got['observations'][0]['completion_display_observed'])
                    self.assertFalse(got['observations'][0]['completion_authenticated'])
                    self.assertFalse(got['observations'][0]['period_authenticated'])

    def test_maximum_three_deterministic_fixed_url_gets_with_no_retries(self):
        rows = ''.join(row(fixture=str(5884 + i), home=str(264 + i), away=str(110 + i),
                           date=f'{16 + i:02d}.10.') for i in range(5))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_source(root / 'raw', rows)
            opener = Mock()
            opener.open.side_effect = lambda request, **kwargs: Response(url=request.full_url)
            with patch('ops.ndr_completion_collector.build_opener', return_value=opener), \
                    patch('ops.ndr_completion_collector.parse_detail', side_effect=self.candidate):
                got = collect(root / 'raw', root / 'out', now=NOW)
            urls = [call.args[0].full_url for call in opener.open.call_args_list]
            self.assertEqual(urls, [f'https://www.ndr.de/sport/ergebnisse/spielstatistik-{fixture}.html'
                                    for fixture in ['5888', '5884', '5885']])
            self.assertEqual(got['attempt_count'], 3)
            self.assertEqual(got['attempt_count'], got['requests_attempted'])
            self.assertEqual(got['max_requests'], 3)
            self.assertEqual(got['observation_count'], 3)

    def test_lower_limit_and_invalid_limits_are_validated_before_http(self):
        for limit in [0, 4, -1, True, '3', None]:
            with self.subTest(limit=limit), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.make_source(root / 'raw')
                with patch('ops.ndr_completion_collector.build_opener') as opener:
                    with self.assertRaises(ValueError):
                        collect(root / 'raw', root / 'out', limit=limit, now=NOW)
                    opener.assert_not_called()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_source(root / 'raw', row() + row(fixture='999', home='999'))
            with patch('ops.ndr_completion_collector.fetch_detail', return_value=(DETAIL, 200, 'text/html', DETAIL_URL)) as fetch, \
                    patch('ops.ndr_completion_collector.parse_detail', side_effect=self.candidate):
                got = collect(root / 'raw', root / 'out', limit=1, now=NOW)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(got['attempt_count'], 1)

    def test_invalid_hash_or_manifest_or_duplicate_identity_requests_nothing(self):
        for attack in ['hash', 'unsafe_manifest', 'duplicate', 'forged_json']:
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                manifest = self.make_source(root / 'raw', row() + row() if attack == 'duplicate' else None)
                if attack == 'hash':
                    (root / 'raw' / 'ndr.html').write_bytes(b'changed')
                elif attack == 'unsafe_manifest':
                    manifest['eligible_for_model_scoring'] = True
                    (root / 'raw' / 'manifest.json').write_text(json.dumps(manifest))
                elif attack == 'forged_json':
                    forged = json.dumps({'observations': [self.candidate(DETAIL, {'fixture_url': DETAIL_URL})]}).encode()
                    (root / 'raw' / 'ndr.html').write_bytes(forged)
                    manifest['sources'][0].update(raw_sha256=hashlib.sha256(forged).hexdigest(), bytes=len(forged))
                    (root / 'raw' / 'manifest.json').write_text(json.dumps(manifest))
                with patch('ops.ndr_completion_collector.build_opener') as opener:
                    got = collect(root / 'raw', root / 'out', now=NOW)
                    opener.assert_not_called()
                self.assertTrue(got['input_rejected'])
                self.assertIsNone(got['selection'])
                self.assertEqual(got['observation_count'], 0)
                self.assertEqual(got['attempt_count'], 0)
                self.assertEqual(got['error'], 'NDR_COMPLETION_SOURCE_INPUT_REJECTED')

    def test_missing_source_is_hold_without_requests_and_without_stale_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.make_source(root / 'raw')
            manifest['sources'] = []
            (root / 'raw' / 'manifest.json').write_text(json.dumps(manifest))
            with patch('ops.ndr_completion_collector.build_opener') as opener:
                got = collect(root / 'raw', root / 'out', now=NOW)
                opener.assert_not_called()
            self.assertFalse(got['source_available'])
            self.assertIsNone(got['selection'])
            self.assertFalse(got['input_rejected'])
            self.assertEqual(got['observation_count'], 0)
            with patch('ops.ndr_completion_collector.build_opener') as opener:
                with self.assertRaises(ValueError):
                    collect(root / 'raw', root / 'out', now=NOW)
                opener.assert_not_called()

    def test_bad_fetch_is_quarantined_and_later_fixture_still_collected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_source(root / 'raw', row() + row(fixture='999', home='999'))
            with patch('ops.ndr_completion_collector.fetch_detail', side_effect=[URLError('DO_NOT_LEAK https://secret.invalid?key=value'),
                    (DETAIL, 200, 'text/html', 'https://www.ndr.de/sport/ergebnisse/spielstatistik-999.html')]) as fetch, \
                    patch('ops.ndr_completion_collector.parse_detail', side_effect=self.candidate):
                got = collect(root / 'raw', root / 'out', now=NOW)
            self.assertEqual(fetch.call_count, 2)
            self.assertEqual(got['attempt_count'], 2)
            self.assertEqual(got['observation_count'], 1)
            self.assertEqual(len(got['fetch_errors']), 1)
            self.assertNotIn('DO_NOT_LEAK', json.dumps(got))
            self.assertNotIn('secret.invalid', json.dumps(got))

    def test_parser_conflicts_preserve_raw_but_never_emit_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_source(root / 'raw')
            with patch('ops.ndr_completion_collector.fetch_detail', return_value=(DETAIL, 200, 'text/html', DETAIL_URL)), \
                    patch('ops.ndr_completion_collector.parse_detail', side_effect=ValueError('DETAIL_SCORE_CONFLICT')):
                got = collect(root / 'raw', root / 'out', now=NOW)
            self.assertEqual(got['observation_count'], 0)
            self.assertEqual(got['rejections'][0]['reason'], 'DETAIL_SCORE_CONFLICT')
            self.assertEqual((root / 'out' / got['sources'][0]['raw_file']).read_bytes(), DETAIL)
            self.assertEqual(got['sources'][0]['status'], 'FETCHED_UNVERIFIED')

    def test_unsafe_parser_flags_cannot_enter_candidates_or_enable_root(self):
        for flag, value in [('independently_verified', True), ('eligible_for_model_scoring', True),
                            ('completion_display_observed', False), ('completion_display_observed', None),
                            ('completion_authenticated', True), ('period_authenticated', True),
                            ('candidate_only', False), ('status', 'READY'),
                            ('production_recommendations', 'ENABLED')]:
            with self.subTest(flag=flag, value=value), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.make_source(root / 'raw')
                def unsafe(raw, item, *, policy):
                    result = self.candidate(raw, item, policy=policy)
                    result[flag] = value
                    return result
                with patch('ops.ndr_completion_collector.fetch_detail', return_value=(DETAIL, 200, 'text/html', DETAIL_URL)), \
                        patch('ops.ndr_completion_collector.parse_detail', side_effect=unsafe):
                    got = collect(root / 'raw', root / 'out', now=NOW)
                self.assertEqual(got['observations'], [])
                self.assertEqual(got['rejections'][0]['reason'], 'UNSAFE_NDR_DETAIL_OBSERVATION')
                self.assertFalse(got['independently_verified'])
                self.assertFalse(got['eligible_for_model_scoring'])
                self.assertEqual(got['production_recommendations'], 'DISABLED')

    def test_redirect_error_counts_one_request_without_persisting_external_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_source(root / 'raw')
            opener = Mock()
            opener.open.side_effect = HTTPError('https://secret.invalid/?token=DO_NOT_LEAK', 302,
                                               'DO_NOT_LEAK', {}, None)
            with patch('ops.ndr_completion_collector.build_opener', return_value=opener) as factory:
                got = collect(root / 'raw', root / 'out', now=NOW)
            self.assertIsInstance(factory.call_args.args[0], _NoRedirects)
            self.assertEqual(opener.open.call_count, 1)
            self.assertEqual(got['requests_attempted'], 1)
            self.assertEqual(got['observation_count'], 0)
            self.assertEqual(got['sources'][0]['http_status'], 302)
            self.assertIsNone(got['sources'][0]['final_url'])
            self.assertNotIn('DO_NOT_LEAK', json.dumps(got))
            self.assertEqual(list((root / 'out').glob('*.html')), [])

    def test_output_inside_input_symlink_hardlink_and_nonempty_directory_rejected_before_http(self):
        for attack in ['nested', 'same', 'symlink', 'symlink_parent', 'hardlink_file', 'nonempty']:
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.make_source(root / 'raw')
                output = root / 'out'
                if attack == 'nested':
                    output = root / 'raw' / 'nested'
                elif attack == 'same':
                    output = root / 'raw'
                elif attack == 'symlink':
                    output.symlink_to(root / 'raw', target_is_directory=True)
                elif attack == 'symlink_parent':
                    (root / 'alias').symlink_to(root / 'raw', target_is_directory=True)
                    output = root / 'alias' / 'out'
                elif attack == 'hardlink_file':
                    output.hardlink_to(root / 'raw' / 'ndr.html')
                else:
                    output.mkdir()
                    (output / 'stale.html').write_text('stale')
                with patch('ops.ndr_completion_collector.build_opener') as opener:
                    with self.assertRaises(ValueError):
                        collect(root / 'raw', output, now=NOW)
                    opener.assert_not_called()

    def test_input_symlinks_and_hardlinks_cannot_trigger_fetches(self):
        for attack in ['raw_symlink', 'manifest_hardlink', 'html_hardlink']:
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.make_source(root / 'raw')
                source = root / 'raw'
                if attack == 'raw_symlink':
                    (root / 'alias').symlink_to(source, target_is_directory=True)
                    source = root / 'alias'
                else:
                    (root / 'duplicate').hardlink_to(source / ('manifest.json' if attack == 'manifest_hardlink' else 'ndr.html'))
                with patch('ops.ndr_completion_collector.build_opener') as opener:
                    got = collect(source, root / 'out', now=NOW)
                    opener.assert_not_called()
                self.assertTrue(got['input_rejected'])

    def test_fetch_forbids_redirect_and_different_final_url(self):
        handler = _NoRedirects()
        self.assertIsNone(handler.redirect_request(None, None, 302, 'Found', {}, 'https://example.invalid/'))
        for url in ['https://evil.invalid/sport/ergebnisse/spielstatistik-5884.html',
                    DETAIL_URL + '?x=1', DETAIL_URL.replace('5884', '999'),
                    DETAIL_URL.replace('https:', 'http:')]:
            with self.subTest(url=url):
                opener = Mock()
                opener.open.return_value = Response(url=url)
                with patch('ops.ndr_completion_collector.build_opener', return_value=opener):
                    with self.assertRaisesRegex(ValueError, 'FINAL_URL'):
                        fetch_detail(DETAIL_URL)

    def test_fetch_validates_allowlist_status_type_encoding_and_byte_limit(self):
        for url in ['http://www.ndr.de/sport/ergebnisse/spielstatistik-5884.html',
                    DETAIL_URL + '?x=1', DETAIL_URL.replace('www.ndr.de', 'www.ndr.de.evil.invalid'),
                    DETAIL_URL.replace('5884', '0'), DETAIL_URL.replace('5884', '../5884')]:
            with self.subTest(url=url), patch('ops.ndr_completion_collector.build_opener') as opener:
                with self.assertRaises(ValueError):
                    fetch_detail(url)
                opener.assert_not_called()
        for response in [Response(status=404), Response(status=True), Response(content_type='application/json'),
                         Response(body=b''), Response(body=b'a' * (MAX_BYTES + 1))]:
            with self.subTest(status=response.status, size=len(response.body)):
                opener = Mock()
                opener.open.return_value = response
                with patch('ops.ndr_completion_collector.build_opener', return_value=opener):
                    with self.assertRaises(ValueError):
                        fetch_detail(DETAIL_URL)

    def test_cli_integrity_error_exits_one_with_safe_zero_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_source(root / 'raw')
            (root / 'raw' / 'ndr.html').write_text('corrupt')
            result = subprocess.run([sys.executable, '-m', 'ops.ndr_completion_collector',
                                     '--raw-dir', str(root / 'raw'), '--output-dir', str(root / 'out')],
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 1, result.stderr)
            report = json.loads((root / 'out' / 'report.json').read_text())
            self.assertEqual(report['observation_count'], 0)
            self.assertEqual(report['status'], 'HOLD')
            self.assertNotIn(str(root), result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
