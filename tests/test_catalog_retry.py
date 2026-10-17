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
