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

    def test_noncanonical_timestamp_rejected(self):
        for ts in ("2026-11-24X09:59:00Z", "20261124T095900Z",
                   "2026-11-24T09:59:00+00:60", "2026-11-24T09:59:00-00:00",
                   "2026-11-24T09:59:00.1234567Z"):
            with self.subTest(ts=ts), self.assertRaisesRegex(ValueError, "INVALID_TIMESTAMP"):
                self.run_intake(collected_at=ts)

    def test_age_cap_cannot_be_relaxed(self):
        for age in (0, True, 901, 40000000):
            with self.subTest(age=age), self.assertRaisesRegex(ValueError, "INVALID_MAX_AGE"):
                intake(self.record, b"x", reviewed_urls={self.url}, now_utc=self.now,
                       max_age_seconds=age)

    def test_internal_suffix_rejected_even_if_reviewed(self):
        for host in ("service.local", "service.internal", "service.localhost",
                     "service.home.arpa", "service.onion"):
            url = "https://" + host + "/news"
            row = dict(self.record, source_url=url, requested_url=url)
            with self.subTest(host=host), self.assertRaisesRegex(ValueError, "INVALID_URL"):
                intake(row, b"x", reviewed_urls={url}, now_utc=self.now)

    def test_offset_equivalence(self):
        result = self.run_intake(collected_at="2026-11-24T17:59:00+08:00")
        self.assertEqual(result["collected_at"], "2026-11-24T09:59:00+00:00")

    def test_deterministic_stress_10000(self):
        import random
        from datetime import datetime, timedelta
        rng = random.Random(585)
        now = datetime.fromisoformat(self.now)
        for i in range(10000):
            kind = i % 10
            body = rng.randbytes(rng.randint(1, 4096))
            row = dict(self.record, status="PASS", source_authorized=True,
                       independently_verified=True, eligible_for_model_scoring=True,
                       production_recommendations="ENABLED", payload_sha256="fake")
            reject = False
            if kind in (3, 4, 5):
                row["source_url"] = f"https://club.example/{i}"
                reject = True
            elif kind in (6, 7, 8, 9):
                offset = rng.randint(-5000, 5000)
                field = "upstream_observed_at" if kind == 9 else "collected_at"
                row[field] = (now + timedelta(seconds=offset)).isoformat()
                reject = not (-900 <= offset <= (-60 if kind == 9 else 0))
            if reject:
                with self.assertRaises(ValueError):
                    intake(row, body, reviewed_urls={self.url}, now_utc=self.now)
            else:
                out = intake(row, body, reviewed_urls={self.url}, now_utc=self.now)
                self.assertEqual(out["status"], "HOLD")
                self.assertEqual(out["production_recommendations"], "DISABLED")
                for key in ("source_authorized", "independently_verified", "eligible_for_model_scoring"):
                    self.assertIs(out[key], False)
                self.assertEqual(out["payload_sha256"], hashlib.sha256(body).hexdigest())


if __name__ == "__main__":
    unittest.main()
