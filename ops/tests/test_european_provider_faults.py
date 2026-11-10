"""Offline fault-injection tests for real provider transport adapter.

All responses are mocked; no paid API calls or network access.
"""
import io
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from ops.odds_market import APIProblem, retrieve


class FakeResponse:
    def __init__(self, payload=b"[]"):
        self.payload = payload
        self.headers = {"x-requests-used": "0", "x-requests-remaining": "500"}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, limit):
        return self.payload[:limit]


class TestEuropeanProviderFaults(unittest.TestCase):
    def test_timeout_network_and_bad_json_fail_closed(self):
        for failure, expected in (
            (TimeoutError("secret-url"), "PROVIDER_NETWORK_ERROR"),
            (URLError("secret-url"), "PROVIDER_NETWORK_ERROR"),
        ):
            with self.subTest(expected=expected):
                with self.assertRaises(APIProblem) as raised:
                    retrieve("/sports/", "secret", opener=lambda *args, **kwargs: (_ for _ in ()).throw(failure))
                self.assertEqual(str(raised.exception), expected)
                self.assertNotIn("secret", str(raised.exception))
        with self.assertRaises(APIProblem) as raised:
            retrieve("/sports/", "secret", opener=lambda *a, **k: FakeResponse(b"not-json"))
        self.assertEqual(str(raised.exception), "PROVIDER_BAD_JSON")

    def test_auth_and_rate_limit_fail_closed(self):
        for status, expected in ((401, "KEY_REJECTED_OR_NOT_AUTHORIZED"),
                                 (403, "KEY_REJECTED_OR_NOT_AUTHORIZED"),
                                 (429, "RATE_LIMITED"), (503, "PROVIDER_HTTP_503")):
            def opener(request, timeout):
                raise HTTPError("redacted", status, "failure", {}, io.BytesIO())
            with self.subTest(status=status):
                with self.assertRaises(APIProblem) as raised:
                    retrieve("/sports/", "secret", opener=opener)
                self.assertEqual(str(raised.exception), expected)
                self.assertNotIn("secret", str(raised.exception))

    def test_oversized_response_rejected(self):
        with patch("ops.odds_market.MAX_BYTES", 16):
            with self.assertRaises(APIProblem) as raised:
                retrieve("/sports/", "secret",
                         opener=lambda *a, **k: FakeResponse(b"[" + b" " * 50 + b"]"))
        self.assertEqual(str(raised.exception), "RESPONSE_TOO_LARGE")

    def test_successful_transport_does_not_spend_odds_credits(self):
        requested = []
        def opener(request, timeout):
            requested.append(request.full_url.split("?")[0])
            return FakeResponse(b"[]")
        result, quota = retrieve("/sports/", "secret", opener=opener)
        self.assertEqual(result, [])
        self.assertEqual(quota["remaining"], 500)
        self.assertEqual(requested, ["https://api.the-odds-api.com/v4/sports/"])


if __name__ == "__main__":
    unittest.main()
