"""The raw index collector records a bounded origin chain, never trusted scores."""
import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from ops import shadow_external_evidence_collector as collector

NOW = datetime(2026, 10, 19, 16, tzinfo=timezone.utc)
URL = collector.SOURCES['NDR']
BODY = b'<html>raw display, not a verified result</html>'


class Response:
    def __init__(self, body=BODY, status=200, media='Text/HTML; charset=UTF-8', url=URL):
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


class ShadowExternalEvidenceCollectorTests(unittest.TestCase):
    def good(self, url):
        return BODY, 200, 'text/html', url

    def assert_safe(self, result):
        self.assertEqual(result['schema'], 'football-king-external-raw-evidence-v2')
        self.assertEqual(result['status'], 'HOLD')
        self.assertIs(result['independently_verified'], False)
        self.assertIs(result['eligible_for_model_scoring'], False)
        self.assertEqual(result['production_recommendations'], 'DISABLED')

    def test_fetch_returns_exact_origin_and_normalized_html_in_one_bounded_get(self):
        response = Response()
        opener = Mock(return_value=response)
        got = collector.fetch(URL, opener=opener)
        self.assertEqual(got, (BODY, 200, 'text/html', URL))
        opener.assert_called_once()
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, URL)
        self.assertEqual(request.get_method(), 'GET')
        self.assertEqual(opener.call_args.kwargs, {'timeout': 15})
        self.assertEqual(response.read_sizes, [collector.MAX_BYTES + 1])

    def test_fetch_rejects_silently_followed_redirect(self):
        opener = Mock(return_value=Response(url='https://example.org/redirected'))
        with self.assertRaisesRegex(ValueError, 'UNEXPECTED_FINAL_URL'):
            collector.fetch(URL, opener=opener)
        opener.assert_called_once()

    def test_default_opener_disables_redirects_before_second_request(self):
        opener = Mock()
        opener.open.return_value = Response()
        with patch.object(collector, 'build_opener', return_value=opener) as builder:
            self.assertEqual(collector.fetch(URL)[3], URL)
        handler = builder.call_args.args[0]
        self.assertIsNone(handler.redirect_request(Request(URL), None, 302, 'Moved', {}, 'https://example.org'))
        opener.open.assert_called_once()

    def test_redirect_handler_raises_http_error_without_followup(self):
        handler = collector._NoRedirects()
        opener = build_opener(handler)
        opener.open = Mock()
        headers = {'location': 'https://example.org'}
        with self.assertRaises(HTTPError) as caught:
            opener.error('http', Request(URL), Mock(), 302, 'Moved', headers)
        self.assertEqual(caught.exception.code, 302)
        opener.open.assert_not_called()

    def test_fetch_rejects_every_non_allowlisted_url_before_get(self):
        invalid = [None, 1, URL + '#fragment', URL + '?extra=1', URL.replace('https:', 'http:'),
                   URL.replace('www.ndr.de', 'www.ndr.de.example.org'), 'https://example.org/']
        for value in invalid:
            with self.subTest(value=value):
                opener = Mock()
                with self.assertRaisesRegex(ValueError, 'INVALID_SOURCE_URL'):
                    collector.fetch(value, opener=opener)
                opener.assert_not_called()

    def test_fetch_rejects_invalid_status_media_and_body(self):
        cases = [(Response(status=True), 'INVALID_HTTP_STATUS'),
                 (Response(status=301), 'NON_200_RESPONSE'),
                 (Response(status=200.0), 'INVALID_HTTP_STATUS'),
                 (Response(media='application/json'), 'NON_HTML_RESPONSE'),
                 (Response(media=None), 'NON_HTML_RESPONSE'),
                 (Response(body=b''), 'EMPTY_OR_INVALID_BODY'),
                 (Response(body='text'), 'EMPTY_OR_INVALID_BODY'),
                 (Response(body=b'x' * (collector.MAX_BYTES + 1)), 'SOURCE_TOO_LARGE')]
        for response, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(ValueError, reason):
                    collector.fetch(URL, opener=Mock(return_value=response))

    def test_both_fixed_sources_accept_xhtml_and_exact_body_limit(self):
        raw = b'x' * collector.MAX_BYTES
        for url in collector.SOURCES.values():
            with self.subTest(url=url):
                response = Response(body=raw, media='Application/XHTML+XML; charset=utf-8', url=url)
                self.assertEqual(collector.fetch(url, opener=Mock(return_value=response)),
                                 (raw, 200, 'application/xhtml+xml', url))
                self.assertEqual(response.read_sizes, [collector.MAX_BYTES + 1])

    def test_collect_exact_v2_shape_two_requests_original_bytes_and_fixed_clock(self):
        with tempfile.TemporaryDirectory() as tmp:
            getter = Mock(side_effect=self.good)
            output = Path(tmp) / 'new' / 'raw'
            result = collector.collect(output, getter=getter, now=NOW)
            self.assert_safe(result)
            self.assertEqual(set(result), {'schema', 'captured_utc', 'status', 'independently_verified',
                                          'eligible_for_model_scoring', 'production_recommendations', 'sources'})
            self.assertEqual(result['captured_utc'], NOW.isoformat())
            self.assertEqual(getter.call_args_list, [unittest.mock.call(url) for url in collector.SOURCES.values()])
            for source in result['sources']:
                self.assertEqual(set(source), {'provider', 'source_url', 'status', 'requested_utc',
                    'completed_utc', 'redirect_policy', 'final_url', 'raw_file', 'raw_sha256',
                    'bytes', 'http_status', 'content_type'})
                self.assertEqual(source['status'], 'FETCHED_UNVERIFIED')
                self.assertEqual(source['requested_utc'], NOW.isoformat())
                self.assertEqual(source['completed_utc'], NOW.isoformat())
                self.assertEqual(source['redirect_policy'], 'DENY_ALL')
                self.assertEqual(source['final_url'], source['source_url'])
                self.assertEqual(source['content_type'], 'text/html')
                self.assertEqual(source['raw_sha256'], hashlib.sha256(BODY).hexdigest())
                self.assertEqual(source['bytes'], len(BODY))
                self.assertEqual((output / source['raw_file']).read_bytes(), BODY)
            self.assertEqual(json.loads((output / 'manifest.json').read_text()), result)

    def test_collect_default_clock_records_serial_request_completion_boundaries(self):
        ticks = [NOW + timedelta(seconds=i) for i in range(5)]
        with tempfile.TemporaryDirectory() as tmp, patch.object(collector, 'datetime') as clock:
            clock.now.side_effect = ticks
            # datetime type checks use the original class through _utc_now's validation.
            clock.side_effect = datetime
            result = collector.collect(Path(tmp) / 'raw', getter=self.good)
        self.assertEqual(result['captured_utc'], ticks[0].isoformat())
        self.assertEqual([source['requested_utc'] for source in result['sources']],
                         [ticks[1].isoformat(), ticks[3].isoformat()])
        self.assertEqual([source['completed_utc'] for source in result['sources']],
                         [ticks[2].isoformat(), ticks[4].isoformat()])

    def test_backward_clock_fails_without_publishing_fabricated_capture_times(self):
        for ticks, expected_calls in [([NOW, NOW - timedelta(seconds=1)], 0),
                                      ([NOW, NOW, NOW - timedelta(seconds=1)], 1)]:
            with self.subTest(expected_calls=expected_calls), tempfile.TemporaryDirectory() as tmp, \
                    patch.object(collector, 'datetime') as clock:
                clock.now.side_effect = ticks
                getter = Mock(side_effect=self.good)
                output = Path(tmp) / 'raw'
                with self.assertRaisesRegex(ValueError, 'COLLECTOR_CLOCK_MOVED_BACKWARDS'):
                    collector.collect(output, getter=getter)
                self.assertEqual(getter.call_count, expected_calls)
                self.assertFalse((output / 'manifest.json').exists())

    def test_collect_revalidates_injected_results_without_preserving_rejected_raw(self):
        bad_results = [(BODY, True, 'text/html', URL), (BODY, 200.0, 'text/html', URL),
                       (BODY, 302, 'text/html', URL), (BODY, 200, 'application/json', URL),
                       (BODY, 200, 'text/html', 'https://example.org'),
                       (BODY, 200, 'text/html', None), (BODY, 200, 'text/html'),
                       (b'', 200, 'text/html', URL), ('text', 200, 'text/html', URL),
                       (b'x' * (collector.MAX_BYTES + 1), 200, 'text/html', URL), None]
        for value in bad_results:
            with self.subTest(value_type=type(value).__name__), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / 'raw'
                result = collector.collect(output, getter=lambda url: value, now=NOW)
                self.assert_safe(result)
                self.assertEqual([entry['status'] for entry in result['sources']], ['ERROR', 'ERROR'])
                self.assertEqual(sorted(path.name for path in output.iterdir()), ['manifest.json'])
                for source in result['sources']:
                    self.assertEqual(set(source), {'provider', 'source_url', 'status', 'requested_utc',
                        'completed_utc', 'redirect_policy', 'final_url', 'error_type', 'error_code', 'http_status'})
                    self.assertIn(source['error_code'], collector.ERROR_CODES)
                    self.assertIsNone(source['final_url'])

    def test_failure_is_source_local_typed_and_has_no_arbitrary_exception_text(self):
        failures = [(HTTPError(URL, 302, 'PRIVATE MESSAGE', {'Location': 'https://private.example'}, None),
                     'HTTP_REDIRECT_REJECTED', 302),
                    (HTTPError(URL, 503, 'PRIVATE MESSAGE', {}, None), 'HTTP_ERROR', 503),
                    (TimeoutError('PRIVATE MESSAGE'), 'SOURCE_TIMEOUT', None),
                    (URLError('PRIVATE MESSAGE'), 'SOURCE_NETWORK_ERROR', None),
                    (OSError('PRIVATE MESSAGE'), 'SOURCE_OS_ERROR', None),
                    (ValueError('PRIVATE MESSAGE'), 'SOURCE_VALUE_ERROR', None),
                    (TypeError('PRIVATE MESSAGE'), 'SOURCE_TYPE_ERROR', None),
                    (RuntimeError('PRIVATE MESSAGE'), 'SOURCE_ERROR', None)]
        for failure, code, status in failures:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as tmp:
                getter = Mock(side_effect=[failure, self.good(collector.SOURCES['NDR'])])
                result = collector.collect(Path(tmp) / 'raw', getter=getter, now=NOW)
                self.assert_safe(result)
                first, second = result['sources']
                self.assertEqual(first['status'], 'ERROR')
                self.assertEqual(first['error_code'], code)
                self.assertEqual(first['http_status'], status)
                self.assertEqual(first['completed_utc'], NOW.isoformat())
                self.assertEqual(second['status'], 'FETCHED_UNVERIFIED')
                self.assertNotIn('PRIVATE', json.dumps(result))
                self.assertNotIn('private.example', json.dumps(result))
                self.assertEqual(getter.call_count, 2)

    def test_invalid_http_error_code_never_becomes_manifest_status(self):
        for status in [True, 99, 600, '302', None]:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                getter = Mock(side_effect=HTTPError(URL, status, 'bad', {}, None))
                got = collector.collect(Path(tmp) / 'raw', getter=getter, now=NOW)
                self.assertTrue(all(entry['http_status'] is None for entry in got['sources']))

    def test_untrusted_exception_type_names_are_not_copied_to_manifest(self):
        arbitrary_error = type('PRIVATE_EXCEPTION_NAME', (Exception,), {})
        with tempfile.TemporaryDirectory() as tmp:
            result = collector.collect(Path(tmp) / 'raw',
                getter=Mock(side_effect=arbitrary_error('PRIVATE MESSAGE')), now=NOW)
            self.assertTrue(all(entry['error_type'] == 'Exception' for entry in result['sources']))
            self.assertNotIn('PRIVATE', json.dumps(result))

    def test_bad_output_is_rejected_before_any_get_and_existing_files_unchanged(self):
        for mode in ['nonempty', 'file', 'symlink', 'parent_symlink', 'hardlink']:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                target = root / 'raw'
                original = root / 'original'
                original.write_bytes(BODY)
                if mode == 'file':
                    target.write_bytes(BODY)
                elif mode == 'symlink':
                    target.symlink_to(root / 'elsewhere', target_is_directory=True)
                elif mode == 'parent_symlink':
                    (root / 'elsewhere').mkdir()
                    target.symlink_to(root / 'elsewhere', target_is_directory=True)
                    target /= 'nested'
                else:
                    target.mkdir()
                    if mode == 'hardlink':
                        os.link(original, target / 'ndr.html')
                    else:
                        (target / 'ndr.html').write_bytes(BODY)
                getter = Mock()
                with self.assertRaises((ValueError, OSError)):
                    collector.collect(target, getter=getter, now=NOW)
                getter.assert_not_called()
                self.assertEqual(original.read_bytes(), BODY)
                if mode == 'file':
                    self.assertEqual(target.read_bytes(), BODY)

    def test_invalid_clock_rejected_before_get(self):
        for now in [datetime(2026, 10, 19), NOW.astimezone(timezone(timedelta(hours=8))), 'now', False]:
            with self.subTest(now=now), tempfile.TemporaryDirectory() as tmp:
                getter = Mock()
                with self.assertRaisesRegex(ValueError, 'INVALID_CURRENT_UTC_TIME'):
                    collector.collect(Path(tmp) / 'raw', getter=getter, now=now)
                getter.assert_not_called()

    def test_exclusive_writer_refuses_late_symlink_or_existing_hardlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / 'original'
            original.write_bytes(BODY)
            output = root / 'out'
            output.mkdir()
            (output / 'ndr.html').symlink_to(original)
            with self.assertRaises((ValueError, OSError)):
                collector._write_new(output, 'ndr.html', b'overwrite')
            (output / 'ndr.html').unlink()
            os.link(original, output / 'ndr.html')
            with self.assertRaises((ValueError, OSError)):
                collector._write_new(output, 'ndr.html', b'overwrite')
            self.assertEqual(original.read_bytes(), BODY)


if __name__ == '__main__':
    unittest.main()
