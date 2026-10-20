"""Synthetic controlled HTTP fixtures; no sporting API requests in tests."""
import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, call, patch
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from ops import shadow_raw_source_collector as collector
from ops.raw_origin_metadata import validate_manifest

NOW = datetime(2026, 10, 20, 10, tzinfo=timezone.utc)
URLS = collector.source_urls(2026)
URL = URLS['OpenLigaDB']
BODIES = {'OpenLigaDB': b'[]', 'OpenFootball': b'{"matches":[]}'}


def good(url):
    provider = next(provider for provider, endpoint in URLS.items() if endpoint == url)
    media = 'text/plain' if provider == 'OpenFootball' else 'application/json'
    return BODIES[provider], 200, media, url


class Response:
    def __init__(self, body=b'[]', status=200, media='Application/JSON; charset=utf-8', url=URL):
        self.body, self.status, self.url = body, status, url
        self.headers = {'Content-Type': media}
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


class ReceiptRegressionTests(unittest.TestCase):
    def test_fetch_records_http_metadata(self):
        opener = Mock(return_value=Response())
        self.assertEqual(collector.fetch(URL, opener=opener), (b'[]', 200, 'application/json', URL))
        opener.assert_called_once()
        self.assertEqual(opener.call_args.kwargs, {'timeout': 15})
        self.assertEqual(opener.call_args.args[0].get_method(), 'GET')
        self.assertEqual(opener.call_args.args[0].full_url, URL)

    def test_followed_redirect_rejected(self):
        response = Response(url='https://example.org/redirected')
        with self.assertRaisesRegex(ValueError, 'UNEXPECTED_FINAL_URL'):
            collector.fetch(URL, opener=Mock(return_value=response))
        self.assertEqual(response.read_sizes, [])

    def test_existing_raw_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'openligadb.json'
            target.write_bytes(b'original')
            getter = Mock(side_effect=good)
            with self.assertRaisesRegex(ValueError, 'FRESH_AND_EMPTY'):
                collector.collect(2026, folder, getter=getter)
            getter.assert_not_called()
            self.assertEqual(target.read_bytes(), b'original')


class CollectorTests(unittest.TestCase):
    def assert_safe(self, manifest):
        self.assertEqual(manifest['schema'], 'football-king-raw-ft-source-candidates-v2')
        self.assertEqual(manifest['status'], 'HOLD')
        self.assertIs(manifest['independently_verified'], False)
        self.assertIs(manifest['eligible_for_model_scoring'], False)
        self.assertEqual(manifest['production_recommendations'], 'DISABLED')
        self.assertIsNone(validate_manifest(manifest, now=NOW))

    def test_raw_bytes_hash_and_hold(self):
        with tempfile.TemporaryDirectory() as folder:
            getter = Mock(side_effect=good)
            manifest = collector.collect(2026, folder, getter=getter, now=NOW)
            self.assert_safe(manifest)
            self.assertEqual(getter.call_args_list, [call(url) for url in URLS.values()])
            self.assertEqual([entry['provider'] for entry in manifest['sources']], list(URLS))
            self.assertEqual(manifest['season_start'], 2026)
            self.assertEqual(manifest['captured_utc'], NOW.isoformat())
            for item in manifest['sources']:
                body = BODIES[item['provider']]
                self.assertEqual(item['raw_sha256'], hashlib.sha256(body).hexdigest())
                self.assertEqual((Path(folder) / item['raw_file']).read_bytes(), body)
                self.assertEqual(item['raw_file'], item['provider'].lower() + '.json')
                self.assertEqual(item['bytes'], len(body))
                self.assertEqual(item['http_status'], 200)
                self.assertEqual(item['final_url'], item['source_url'])
                self.assertEqual(item['redirect_policy'], 'DENY_ALL')
            self.assertEqual(json.loads((Path(folder) / 'manifest.json').read_bytes()), manifest)

    def test_capture_timestamp_normalized_to_utc(self):
        with tempfile.TemporaryDirectory() as folder:
            stamp = NOW.astimezone(timezone(timedelta(hours=8)))
            result = collector.collect(2026, folder, getter=good, now=stamp)
            self.assertEqual(result['captured_utc'], NOW.isoformat())
            self.assert_safe(result)

    def test_naive_capture_rejected_before_get(self):
        for value in [datetime(2026, 10, 14), 'now', False]:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as folder:
                getter = Mock()
                with self.assertRaisesRegex(ValueError, 'INVALID_CAPTURE_TIME'):
                    collector.collect(2026, folder, getter=getter, now=value)
                getter.assert_not_called()

    def test_real_clock_records_every_serial_boundary(self):
        ticks = [NOW + timedelta(seconds=i) for i in range(5)]
        with tempfile.TemporaryDirectory() as folder, patch.object(collector, 'datetime') as clock:
            clock.now.side_effect = ticks
            result = collector.collect(2026, folder, getter=good)
        self.assertEqual(result['captured_utc'], ticks[0].isoformat())
        self.assertEqual([entry['requested_utc'] for entry in result['sources']],
                         [ticks[1].isoformat(), ticks[3].isoformat()])
        self.assertEqual([entry['completed_utc'] for entry in result['sources']],
                         [ticks[2].isoformat(), ticks[4].isoformat()])
        self.assertIsNone(validate_manifest(result, now=ticks[-1]))

    def test_backwards_clock_cleans_all_exclusive_creations(self):
        cases = [([NOW, NOW - timedelta(seconds=1)], 0),
                 ([NOW, NOW, NOW - timedelta(seconds=1)], 1),
                 ([NOW, NOW, NOW, NOW - timedelta(seconds=1)], 1),
                 ([NOW, NOW, NOW, NOW, NOW - timedelta(seconds=1)], 2)]
        for ticks, expected_calls in cases:
            with self.subTest(calls=expected_calls, ticks=len(ticks)), tempfile.TemporaryDirectory() as folder, \
                    patch.object(collector, 'datetime') as clock:
                clock.now.side_effect = ticks
                getter = Mock(side_effect=good)
                with self.assertRaisesRegex(ValueError, 'COLLECTOR_CLOCK_MOVED_BACKWARDS'):
                    collector.collect(2026, folder, getter=getter)
                self.assertEqual(getter.call_count, expected_calls)
                self.assertEqual(list(Path(folder).iterdir()), [])

    def test_malformed_response_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = collector.collect(2026, folder,
                getter=lambda url: (b'not-json', 200, 'application/json', url), now=NOW)
            self.assertEqual([s['status'] for s in manifest['sources']], ['ERROR', 'ERROR'])
            self.assertTrue(all(s['error_code'] == 'INVALID_JSON' for s in manifest['sources']))
            self.assert_safe(manifest)
            self.assertEqual(sorted(path.name for path in Path(folder).iterdir()), ['manifest.json'])

    def test_byte_only_getter_cannot_fabricate_a_transport_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            result = collector.collect(2026, folder, getter=lambda url: b'[]', now=NOW)
            self.assert_safe(result)
            for source in result['sources']:
                self.assertEqual(source['error_code'], 'INVALID_FETCH_RESULT')
                self.assertIsNone(source['final_url'])
                self.assertIsNone(source['http_status'])
                self.assertNotIn('raw_file', source)

    def test_injected_transport_revalidated_for_both_providers(self):
        cases = [lambda u: None, lambda u: [], lambda u: (b'[]', 200, 'application/json'),
                 lambda u: (b'[]', True, 'application/json', u),
                 lambda u: (b'[]', 200.0, 'application/json', u),
                 lambda u: (b'[]', 301, 'application/json', u),
                 lambda u: (b'[]', 503, 'application/json', u),
                 lambda u: (b'[]', 200, 'text/html', u),
                 lambda u: (b'[]', 200, None, u),
                 lambda u: (b'[]', 200, 'application/json', u + '?alternate=1'),
                 lambda u: (b'[]', 200, 'application/json', None),
                 lambda u: (b'', 200, 'application/json', u),
                 lambda u: ('[]', 200, 'application/json', u),
                 lambda u: (b' ' * (collector.MAX_BYTES + 1), 200, 'application/json', u)]
        for index, getter in enumerate(cases):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as folder:
                result = collector.collect(2026, folder, getter=getter, now=NOW)
                self.assert_safe(result)
                self.assertEqual([entry['status'] for entry in result['sources']], ['ERROR', 'ERROR'])
                self.assertEqual(sorted(path.name for path in Path(folder).iterdir()), ['manifest.json'])

    def test_safe_source_local_errors_never_retry_or_copy_sensitive_text(self):
        failures = [(HTTPError(URL, 302, 'PRIVATE MESSAGE', {'Location': 'https://private.example'}, None),
                     'HTTP_REDIRECT_REJECTED', 302),
                    (HTTPError(URL, 503, 'PRIVATE MESSAGE', {}, None), 'HTTP_ERROR', 503),
                    (TimeoutError('PRIVATE MESSAGE'), 'SOURCE_TIMEOUT', None),
                    (URLError(TimeoutError('PRIVATE MESSAGE')), 'SOURCE_TIMEOUT', None),
                    (URLError('PRIVATE MESSAGE'), 'SOURCE_NETWORK_ERROR', None),
                    (OSError('PRIVATE MESSAGE'), 'SOURCE_OS_ERROR', None),
                    (ValueError('PRIVATE MESSAGE'), 'SOURCE_VALUE_ERROR', None),
                    (TypeError('PRIVATE MESSAGE'), 'SOURCE_TYPE_ERROR', None),
                    (RuntimeError('PRIVATE MESSAGE'), 'SOURCE_ERROR', None)]
        for error, code, status in failures:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as folder:
                getter = Mock(side_effect=[error, good(URLS['OpenFootball'])])
                result = collector.collect(2026, folder, getter=getter, now=NOW)
                self.assert_safe(result)
                first, second = result['sources']
                self.assertEqual(first['error_code'], code)
                self.assertEqual(first['http_status'], status)
                self.assertIsNone(first['final_url'])
                self.assertEqual(second['status'], 'FETCHED_UNVERIFIED')
                self.assertEqual(getter.call_count, 2)
                self.assertNotIn('PRIVATE', json.dumps(result))
                self.assertNotIn('private.example', json.dumps(result))

    def test_arbitrary_exception_class_and_invalid_http_status_are_sanitized(self):
        arbitrary = type('PRIVATE_EXCEPTION', (Exception,), {})
        errors = [arbitrary('PRIVATE MESSAGE')]
        errors += [HTTPError(URL, value, 'PRIVATE MESSAGE', {}, None) for value in [True, '302', 99, 600, None]]
        for error in errors:
            with self.subTest(kind=type(error).__name__), tempfile.TemporaryDirectory() as folder:
                result = collector.collect(2026, folder, getter=Mock(side_effect=error), now=NOW)
                self.assert_safe(result)
                self.assertNotIn('PRIVATE', json.dumps(result))
                self.assertTrue(all(s['http_status'] is None for s in result['sources']))

    def test_fresh_output_aliases_and_links_rejected_before_any_get(self):
        for mode in ['file', 'nonempty', 'symlink', 'parent_symlink', 'hardlink', 'dotdot']:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                original = root / 'original'
                original.write_bytes(b'original')
                output = root / 'raw'
                if mode == 'file':
                    output.write_bytes(b'original')
                elif mode == 'symlink':
                    output.symlink_to(root / 'elsewhere', target_is_directory=True)
                elif mode == 'parent_symlink':
                    (root / 'elsewhere').mkdir()
                    output.symlink_to(root / 'elsewhere', target_is_directory=True)
                    output /= 'nested'
                elif mode == 'dotdot':
                    output = root / 'nested' / '..' / 'raw'
                else:
                    output.mkdir()
                    if mode == 'hardlink':
                        os.link(original, output / 'openligadb.json')
                    else:
                        (output / 'manifest.json').write_bytes(b'original')
                getter = Mock()
                with self.assertRaises((ValueError, OSError)):
                    collector.collect(2026, output, getter=getter, now=NOW)
                getter.assert_not_called()
                self.assertEqual(original.read_bytes(), b'original')

    def test_late_output_alias_fails_exclusively_and_cleans_prior_raw(self):
        for mode in ['symlink', 'hardlink', 'existing']:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                original = root / 'original'
                original.write_bytes(b'original')
                output = root / 'raw'

                def inject(url):
                    if url == URLS['OpenFootball']:
                        target = output / 'openfootball.json'
                        if mode == 'symlink':
                            target.symlink_to(original)
                        elif mode == 'hardlink':
                            os.link(original, target)
                        else:
                            target.write_bytes(b'original')
                    return good(url)

                with self.assertRaises(OSError):
                    collector.collect(2026, output, getter=inject, now=NOW)
                self.assertEqual(original.read_bytes(), b'original')
                self.assertFalse((output / 'openligadb.json').exists())
                self.assertFalse((output / 'manifest.json').exists())
                self.assertEqual((output / 'openfootball.json').read_bytes(), b'original')

    def test_manifest_write_failure_cleans_all_raw_files(self):
        original = collector._write_new
        def fail_manifest(folder, filename, raw):
            if filename == 'manifest.json':
                raise PermissionError('unsafe write')
            return original(folder, filename, raw)
        with tempfile.TemporaryDirectory() as folder, patch.object(collector, '_write_new', side_effect=fail_manifest):
            with self.assertRaises(PermissionError):
                collector.collect(2026, folder, getter=good, now=NOW)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_season_range_and_boolean_rejected_before_get(self):
        for year in [True, False, 1999, 2101, 2026.0, '2026', None]:
            with self.subTest(year=year), tempfile.TemporaryDirectory() as folder:
                getter = Mock()
                with self.assertRaisesRegex(ValueError, 'INVALID_SEASON'):
                    collector.collect(year, folder, getter=getter, now=NOW)
                getter.assert_not_called()
        for year, suffix in [(2000, '2000-01'), (2099, '2099-00'), (2100, '2100-01')]:
            self.assertIn('/' + suffix + '/de.1.json', collector.source_urls(year)['OpenFootball'])


class FetchTests(unittest.TestCase):
    def test_default_opener_disables_redirects_before_second_request(self):
        opener = Mock()
        opener.open.return_value = Response()
        with patch.object(collector, 'build_opener', return_value=opener) as builder:
            self.assertEqual(collector.fetch(URL)[3], URL)
        handler = builder.call_args.args[0]
        self.assertIsNone(handler.redirect_request(Request(URL), None, 302, 'Moved', {}, 'https://example.org'))
        opener.open.assert_called_once()

    def test_real_redirect_handler_never_forwards_to_location(self):
        for code in [301, 302, 303, 307, 308]:
            with self.subTest(code=code):
                opener = build_opener(collector._NoRedirects())
                opener.open = Mock()
                with self.assertRaises(HTTPError) as caught:
                    opener.error('http', Request(URL), Mock(), code, 'Moved',
                                 {'Location': 'https://private.example'})
                self.assertEqual(caught.exception.code, code)
                opener.open.assert_not_called()

    def test_fixed_url_templates_reject_every_alias_before_get(self):
        invalid = [None, 1, URL + '#fragment', URL + '?extra=1', URL + '/',
                   URL.replace('https:', 'http:'), URL.replace('2026', '02026'),
                   URL.replace('2026', '1999'), URL.replace('2026', '2101'),
                   URL.replace('openligadb.de', 'openligadb.de.example.org'),
                   URLS['OpenFootball'].replace('2026-27', '2026-28'),
                   URLS['OpenFootball'].replace('/master/', '/main/'),
                   'https://example.org/']
        for value in invalid:
            with self.subTest(value=value):
                opener = Mock()
                with self.assertRaisesRegex(ValueError, 'INVALID_SOURCE_URL'):
                    collector.fetch(value, opener=opener)
                opener.assert_not_called()

    def test_status_media_body_and_schema_fail_closed(self):
        cases = [(Response(status=True), 'INVALID_HTTP_STATUS'),
                 (Response(status=200.0), 'INVALID_HTTP_STATUS'),
                 (Response(status=302), 'NON_200_RESPONSE'),
                 (Response(status=204), 'NON_200_RESPONSE'),
                 (Response(media='text/plain'), 'NON_JSON_RESPONSE'),
                 (Response(media='application/problem+json'), 'NON_JSON_RESPONSE'),
                 (Response(media=None), 'NON_JSON_RESPONSE'),
                 (Response(body=b''), 'EMPTY_OR_INVALID_BODY'),
                 (Response(body='[]'), 'EMPTY_OR_INVALID_BODY'),
                 (Response(body=b' ' * (collector.MAX_BYTES + 1)), 'SOURCE_TOO_LARGE'),
                 (Response(body=b'{}'), 'UNEXPECTED_OPENLIGADB_SCHEMA'),
                 (Response(body=b'NaN'), 'INVALID_JSON'),
                 (Response(body=b'[{"x":1,"x":2}]'), 'INVALID_JSON')]
        for response, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(ValueError, reason):
                    collector.fetch(URL, opener=Mock(return_value=response))

    def test_actual_header_shape_and_openfootball_plain_text_exception(self):
        for provider, url in URLS.items():
            for media in ['Application/JSON; charset=utf-8', 'text/plain; charset=utf-8']:
                with self.subTest(provider=provider, media=media):
                    response = Response(body=BODIES[provider], media=media, url=url)
                    if provider == 'OpenLigaDB' and media.startswith('text/plain'):
                        with self.assertRaisesRegex(ValueError, 'NON_JSON_RESPONSE'):
                            collector.fetch(url, opener=Mock(return_value=response))
                        self.assertEqual(response.read_sizes, [])
                    else:
                        got = collector.fetch(url, opener=Mock(return_value=response))
                        self.assertEqual(got, (BODIES[provider], 200, media.split(';')[0].lower(), url))
                        self.assertEqual(response.read_sizes, [collector.MAX_BYTES + 1])

    def test_exact_three_megabyte_valid_json_accepted(self):
        raw = b'[]' + b' ' * (collector.MAX_BYTES - 2)
        response = Response(body=raw)
        self.assertEqual(collector.fetch(URL, opener=Mock(return_value=response))[0], raw)
        self.assertEqual(response.read_sizes, [collector.MAX_BYTES + 1])

    def test_nonfinite_duplicate_nested_keys_wrong_json_and_provider_shapes(self):
        malformed = [b'[{"x":NaN}]', b'[{"x":Infinity}]', b'[{"x":-Infinity}]',
                     b'[{"x":1e999}]', b'[{"x":-1e999}]', b'[{"x":{"a":1,"a":2}}]',
                     b'\xff', b'[] trailing', b'']
        for raw in malformed:
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(ValueError, 'INVALID_JSON'):
                    collector.validate_json_body(raw, 'OpenLigaDB')
        with self.assertRaisesRegex(ValueError, 'UNEXPECTED_OPENLIGADB_SCHEMA'):
            collector.validate_json_body(b'{"matches":[]}', 'OpenLigaDB')
        for raw in [b'[]', b'{}', b'{"matches":{}}', b'{"matches":null}']:
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, 'UNEXPECTED_OPENFOOTBALL_SCHEMA'):
                collector.validate_json_body(raw, 'OpenFootball')


if __name__ == '__main__':
    unittest.main()
