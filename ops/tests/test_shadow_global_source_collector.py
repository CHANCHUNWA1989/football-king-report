import hashlib
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener
import shadow_global_source_collector as global_collector
from shadow_raw_source_collector import FetchValidationError
from shadow_global_source_collector import LEAGUES,collect


class Response:
    def __init__(self, url, body=b'{"matches":[]}', status=200, media='text/plain; charset=utf-8'):
        self.url, self.body, self.status = url, body, status
        self.headers = {'Content-Type': media}
        self.read_sizes = []

    def geturl(self): return self.url
    def read(self, size):
        self.read_sizes.append(size)
        return self.body[:size]
    def __enter__(self): return self
    def __exit__(self, *args): return False

class GlobalCollectorTests(unittest.TestCase):
    def test_default_fetch_keeps_bytes_contract_for_all_six_fixed_urls(self):
        for code in LEAGUES.values():
            url = f'{global_collector.BASE}/2026-27/{code}.json'
            response = Response(url)
            opener = Mock(return_value=response)
            with self.subTest(code=code):
                self.assertEqual(global_collector.fetch(url, opener=opener), b'{"matches":[]}')
                self.assertEqual(response.read_sizes, [3_000_001])
                opener.assert_called_once()
                self.assertEqual(opener.call_args.kwargs, {'timeout': 15})
                self.assertEqual(opener.call_args.args[0].full_url, url)

    def test_string_validation_code_cannot_crash_per_league_error_handler(self):
        with tempfile.TemporaryDirectory() as folder:
            result = collect(2026, folder, getter=Mock(side_effect=FetchValidationError('INVALID_SOURCE_URL')))
            self.assertEqual(len(result['leagues']), 6)
            self.assertTrue(all(row['status'] == 'ERROR' for row in result['leagues']))
            self.assertTrue(all('http_status' not in row for row in result['leagues']))

    def test_only_real_integer_http_status_recorded(self):
        for status in [503, '503', True, 99, 600, None]:
            error = HTTPError('https://private.example', status, 'PRIVATE MESSAGE', {}, None)
            with self.subTest(status=status), tempfile.TemporaryDirectory() as folder:
                result = collect(2026, folder, getter=Mock(side_effect=error))
                for row in result['leagues']:
                    if type(status) is int and 100 <= status <= 599:
                        self.assertEqual(row['http_status'], status)
                    else:
                        self.assertNotIn('http_status', row)

    def test_collect_default_transport_gets_exact_six_once_and_preserves_bytes(self):
        urls = list(global_collector.source_urls(2026).values())
        opener = Mock()
        opener.open.side_effect = [Response(url) for url in urls]
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(global_collector, 'build_opener', return_value=opener) as builder:
            result = collect(2026, folder, now=datetime(2026, 10, 20, tzinfo=timezone.utc))
            self.assertEqual([entry['status'] for entry in result['leagues']], ['FETCHED_UNVERIFIED'] * 6)
            self.assertEqual([entry['source_url'] for entry in result['leagues']], urls)
            self.assertEqual(opener.open.call_count, 6)
            self.assertEqual(builder.call_count, 6)
            for args in builder.call_args_list:
                self.assertIsInstance(args.args[0], global_collector._NoRedirects)
            for entry in result['leagues']:
                self.assertEqual((Path(folder) / entry['raw_file']).read_bytes(), b'{"matches":[]}')
                self.assertIs(result['independently_verified'], False)
                self.assertIs(result['eligible_for_model_scoring'], False)
                self.assertEqual(result['production_recommendations'], 'DISABLED')

    def test_six_endpoint_season_range_and_aliases_are_exact(self):
        for year, season in [(2000, '2000-01'), (2026, '2026-27'),
                             (2099, '2099-00'), (2100, '2100-01')]:
            urls = global_collector.source_urls(year)
            self.assertEqual(set(urls), set(LEAGUES))
            for league, code in LEAGUES.items():
                url = f'{global_collector.BASE}/{season}/{code}.json'
                self.assertEqual(urls[league], url)
                with self.subTest(url=url):
                    self.assertEqual(global_collector.fetch(url, opener=Mock(return_value=Response(url))),
                                     b'{"matches":[]}')
        url = global_collector.source_urls(2026)['eng-premier']
        invalid = [None, 1, url + '?key=1', url + '#fragment', url + '/',
                   url.replace('https:', 'http:'), url.replace('/master/', '/main/'),
                   url.replace('2026-27', '2026-28'), url.replace('2026-27', '1999-00'),
                   url.replace('2026-27', '2101-02'), url.replace('en.1.json', 'en.3.json'),
                   url.replace('raw.githubusercontent.com', 'raw.githubusercontent.com.example.org'),
                   'https://api.openligadb.de/getmatchdata/bl1/2026']
        for value in invalid:
            opener = Mock()
            with self.subTest(url=value), self.assertRaisesRegex(ValueError, 'INVALID_SOURCE_URL'):
                global_collector.fetch(value, opener=opener)
            opener.assert_not_called()

    def test_redirect_handler_never_performs_second_request(self):
        for code in [301, 302, 303, 307, 308]:
            opener = build_opener(global_collector._NoRedirects())
            opener.open = Mock()
            with self.subTest(code=code), self.assertRaises(HTTPError):
                opener.error('http', Request(global_collector.source_urls(2026)['eng-premier']),
                             Mock(), code, 'Moved', {'Location': 'https://private.example'})
            opener.open.assert_not_called()

    def test_http_status_media_and_final_url_checked_before_body_read(self):
        url = global_collector.source_urls(2026)['eng-premier']
        cases = [(True, 'application/json', url), (200.0, 'application/json', url),
                 (302, 'application/json', url), (503, 'application/json', url),
                 (200, 'text/html', url), (200, None, url),
                 (200, 'application/json', url + '?alias=1')]
        for status, media, final in cases:
            response = Response(final, status=status, media=media)
            with self.subTest(status=status, media=media, final=final), self.assertRaises(ValueError):
                global_collector.fetch(url, opener=Mock(return_value=response))
            self.assertEqual(response.read_sizes, [])
        for media in ['application/json', 'Application/JSON; charset=utf-8', 'text/plain; charset=utf-8']:
            with self.subTest(media=media):
                self.assertEqual(global_collector.fetch(url, opener=Mock(return_value=Response(url, media=media))),
                                 b'{"matches":[]}')

    def test_body_limit_json_and_shape_checked_on_network_and_injected_getter(self):
        url = global_collector.source_urls(2026)['eng-premier']
        malformed = [b'', 'not-bytes', b' ' * 3_000_001, b'[]', b'{}', b'{"matches":{}}',
                     b'{"matches":[],"matches":[]}', b'{"matches":[{"x":NaN}]}',
                     b'{"matches":[{"x":1e999}]}', b'not-json']
        for raw in malformed:
            with self.subTest(raw_type=type(raw).__name__, size=len(raw)):
                with self.assertRaises(ValueError):
                    global_collector.fetch(url, opener=Mock(return_value=Response(url, body=raw)))
                with tempfile.TemporaryDirectory() as folder:
                    result = collect(2026, folder, getter=lambda endpoint: raw)
                    self.assertTrue(all(row['status'] == 'ERROR' for row in result['leagues']))
                    self.assertEqual(sorted(path.name for path in Path(folder).iterdir()), ['manifest.json'])
        raw = b'{"matches":[]}' + b' ' * (3_000_000 - len(b'{"matches":[]}'))
        self.assertEqual(global_collector.fetch(url, opener=Mock(return_value=Response(url, body=raw))), raw)

    def test_six_leagues_remain_unverified(self):
        raw=b'{"matches":[{"date":"2026-10-14"}]}'
        with tempfile.TemporaryDirectory() as folder:
            result=collect(2026,folder,getter=lambda url:raw,
                           now=datetime(2026,10,14,tzinfo=timezone.utc))
            self.assertEqual(len(result["leagues"]),6)
            self.assertEqual(set(LEAGUES),{x["league"] for x in result["leagues"]})
            self.assertFalse(result["eligible_for_model_scoring"])
            self.assertFalse(result["independently_verified"])
            self.assertEqual(result["production_recommendations"],"DISABLED")
            for item in result["leagues"]:
                self.assertEqual(item["raw_sha256"],hashlib.sha256(raw).hexdigest())
                self.assertEqual((Path(folder)/item["raw_file"]).read_bytes(),raw)
    def test_bad_payload_quarantined_per_league(self):
        with tempfile.TemporaryDirectory() as folder:
            result=collect(2026,folder,getter=lambda url:b"not-json")
            self.assertEqual(len(result["leagues"]),6)
            self.assertTrue(all(x["status"]=="ERROR" for x in result["leagues"]))
    def test_invalid_year_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            for year in (True,1999,2101):
                with self.subTest(year=year),self.assertRaisesRegex(ValueError,"INVALID_SEASON"):
                    collect(year,folder)
if __name__=="__main__":
    unittest.main()
