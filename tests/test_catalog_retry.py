import unittest
from urllib.error import HTTPError
from io import BytesIO
from research_quality.public_catalog import fetch_catalog, MAX_BYTES

class _Response:
    def __init__(self, data): self.data = data
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, size):
        assert size == MAX_BYTES + 1
        return self.data[:size]

class RetryTests(unittest.TestCase):
    def test_transient_http_retried(self):
        calls = []
        def opener(request, timeout):
            calls.append(timeout)
            if len(calls) == 1:
                raise HTTPError(request.full_url, 503, "unavailable", {}, None)
            return _Response(b'{"leagues":[]}' )
        self.assertIsInstance(fetch_catalog(opener=opener, sleep=lambda _: None), list)
        self.assertEqual(len(calls), 2)
    def test_nontransient_not_retried(self):
        calls = []
        def opener(request, timeout):
            calls.append(1)
            raise HTTPError(request.full_url, 403, "forbidden", {}, None)
        with self.assertRaises(HTTPError):
            fetch_catalog(opener=opener, sleep=lambda _: None)
        self.assertEqual(len(calls), 1)
    def test_attempt_cap(self):
        with self.assertRaises(ValueError):
            fetch_catalog(attempts=100)

    def test_connection_reset_recovers(self):
        calls = []
        def opener(request, timeout):
            calls.append(timeout)
            if len(calls) == 1:
                raise ConnectionResetError("temporary reset")
            return _Response(b'{"leagues":[]}')
        self.assertEqual(fetch_catalog(opener=opener, sleep=lambda _: None), [])
        self.assertEqual(len(calls), 2)

    def test_connection_refused_exhausts_attempts(self):
        calls = []
        def opener(request, timeout):
            calls.append(timeout)
            raise ConnectionRefusedError("connection refused")
        with self.assertRaises(ConnectionRefusedError):
            fetch_catalog(opener=opener, sleep=lambda _: None)
        self.assertEqual(len(calls), 2)

    def test_malformed_json_does_not_retry(self):
        calls = []
        def opener(request, timeout):
            calls.append(timeout)
            return _Response(b'not-json')
        with self.assertRaises(ValueError):
            fetch_catalog(opener=opener, sleep=lambda _: None)
        self.assertEqual(len(calls), 1)

    def test_oversized_payload_rejected_without_retry(self):
        calls = []
        def opener(request, timeout):
            calls.append(timeout)
            return _Response(b"x" * (MAX_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "CATALOG_SIZE_LIMIT"):
            fetch_catalog(opener=opener, sleep=lambda _: None)
        self.assertEqual(len(calls), 1)

    def test_invalid_catalog_shape_rejected_without_retry(self):
        calls = []
        def opener(request, timeout):
            calls.append(timeout)
            return _Response(b'{"leagues":{}}')
        with self.assertRaisesRegex(ValueError, "INVALID_LEAGUE_CATALOG"):
            fetch_catalog(opener=opener, sleep=lambda _: None)
        self.assertEqual(len(calls), 1)

    def test_non_soccer_leagues_filtered(self):
        def opener(request, timeout):
            return _Response(b'{"leagues":[{"idLeague":"1","strLeague":"Premier League","strSport":"Soccer"},{"idLeague":"2","strLeague":"NBA","strSport":"Basketball"}]}')
        self.assertEqual(fetch_catalog(opener=opener, sleep=lambda _: None), [{"id":"1","name":"Premier League"}])

    def test_retry_disabled_attempts_one(self):
        calls = []
        def opener(request, timeout):
            calls.append(timeout)
            raise ConnectionResetError("reset")
        with self.assertRaises(ConnectionResetError):
            fetch_catalog(opener=opener, sleep=lambda _: None, attempts=1)
        self.assertEqual(len(calls), 1)
