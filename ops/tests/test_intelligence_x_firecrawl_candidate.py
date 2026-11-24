import hashlib
import unittest

from intelligence_x_firecrawl_candidate import intake, MAX_BYTES


class FirecrawlCandidateTests(unittest.TestCase):
    def setUp(self):
        self.url = "https://club.example/news"
        self.now = "2026-11-24T10:00:00+00:00"
        self.record = dict(collector="firecrawl", requested_url=self.url,
                           source_url=self.url, status_code=200,
                           collected_at="2026-11-24T09:59:00+00:00")

    def run_intake(self, body=b"synthetic news", **changes):
        return intake(dict(self.record, **changes), body,
                      reviewed_urls={self.url}, now_utc=self.now)

    def test_candidate_is_never_certified(self):
        result = self.run_intake(source_authorized=True, independently_verified=True,
                                 eligible_for_model_scoring=True, status="PASS")
        self.assertEqual(result["status"], "HOLD")
        for key in ("source_authorized", "independently_verified", "eligible_for_model_scoring"):
            self.assertIs(result[key], False)
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertEqual(result["payload_sha256"], hashlib.sha256(b"synthetic news").hexdigest())
        self.assertIn("UPSTREAM_CLOCK_MISSING", result["reasons"])
        self.assertNotIn("body", result)

    def test_upstream_claim_does_not_certify(self):
        result = self.run_intake(upstream_observed_at="2026-11-24T09:58:00Z")
        self.assertIn("UPSTREAM_CLOCK_UNVERIFIED", result["reasons"])
        self.assertFalse(result["independently_verified"])

    def test_redirect_or_wrong_url(self):
        for url in ("https://other.example/news", "https://club.example/other",
                    "https://club.example.evil/news"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "URL_NOT_REVIEWED"):
                self.run_intake(source_url=url)

    def test_malformed_urls(self):
        for url in ("http://club.example/news", "https://club.example:443/news",
                    "https://user@club.example/news", "https://club.example/news?x=1",
                    "https://club.example/news#x", "https://club.example/a/../news",
                    "https://club.example/%2e%2e/news", "https://127.0.0.1/news",
                    "https://club.example/news\n"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "INVALID_URL"):
                self.run_intake(source_url=url)

    def test_missing_allowlist(self):
        with self.assertRaisesRegex(ValueError, "REVIEWED_URLS_REQUIRED"):
            intake(self.record, b"x", reviewed_urls=set(), now_utc=self.now)

    def test_bad_http_status(self):
        for status in (True, "200", 301, 403, 429, 500):
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "HTTP_STATUS"):
                self.run_intake(status_code=status)

    def test_invalid_body(self):
        for body in (b"", b"x" * (MAX_BYTES + 1), "text", bytearray(b"x")):
            with self.subTest(kind=type(body)), self.assertRaisesRegex(ValueError, "INVALID_BODY"):
                self.run_intake(body)

    def test_stale_or_future_collection(self):
        for timestamp in ("2026-11-24T09:00:00Z", "2026-11-24T10:01:00Z"):
            with self.subTest(timestamp=timestamp), self.assertRaisesRegex(ValueError, "COLLECTION_CLOCK"):
                self.run_intake(collected_at=timestamp)

    def test_invalid_collection_time(self):
        for timestamp in (None, "bad", "2026-11-24T09:59:00"):
            with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                self.run_intake(collected_at=timestamp)

    def test_stale_or_future_upstream(self):
        for timestamp in ("2026-11-24T09:00:00Z", "2026-11-24T09:59:30Z"):
            with self.subTest(timestamp=timestamp), self.assertRaisesRegex(ValueError, "UPSTREAM_CLOCK"):
                self.run_intake(upstream_observed_at=timestamp)

    def test_wrong_collector(self):
        with self.assertRaisesRegex(ValueError, "INVALID_ENVELOPE"):
            self.run_intake(collector="other")

    def test_maximum_body_and_clock_boundary(self):
        result = self.run_intake(b"x" * MAX_BYTES, collected_at="2026-11-24T09:45:00Z")
        self.assertEqual(result["payload_bytes"], MAX_BYTES)
        self.assertEqual(result["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
