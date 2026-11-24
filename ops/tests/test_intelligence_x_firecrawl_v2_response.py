import copy
import hashlib
import json
import unittest
from intelligence_x_firecrawl_v2_response import normalize_response, MAX_BYTES


class FirecrawlV2ResponseTests(unittest.TestCase):
    def setUp(self):
        self.url = "https://club.example/news"
        self.obj = {"success": True, "data": {"markdown": "Synthetic team news",
                    "metadata": {"sourceURL": self.url, "url": self.url,
                                 "statusCode": 200}}}
        self.kw = dict(requested_url=self.url, reviewed_urls={self.url},
                       collected_at="2026-11-24T09:59:00Z",
                       now_utc="2026-11-24T10:00:00Z", http_status=200)

    def parse(self, obj=None, raw=None, **kw):
        if raw is None:
            raw = json.dumps(self.obj if obj is None else obj).encode()
        return normalize_response(raw, **dict(self.kw, **kw))

    def test_exact_bytes_hash_and_hold(self):
        raw = json.dumps(self.obj, indent=2).encode()
        result = self.parse(raw=raw)
        self.assertEqual(result["payload_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result["payload_kind"], "firecrawl_v2_api_response_bytes")
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertIsNone(result["upstream_observed_at"])
        self.assertFalse(result["independently_verified"])
        self.assertFalse(result["source_authorized"])
        self.assertFalse(result["eligible_for_model_scoring"])
        self.assertNotIn("markdown", result)

    def test_http_failures(self):
        for status in (True, 302, 400, 402, 403, 429, 500, 503):
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "API_HTTP"):
                self.parse(http_status=status)

    def test_unsuccessful_api(self):
        for success in (False, 1, "true", None):
            obj = dict(self.obj, success=success)
            with self.subTest(success=success), self.assertRaisesRegex(ValueError, "API_RESPONSE"):
                self.parse(obj)

    def test_malformed_or_duplicate_json(self):
        for raw in (b"{", b"\xff", b'{"success":true,"success":false}',
                    b'{"data":{"url":1,"url":2}}', b'{"x":NaN}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.parse(raw=raw)

    def test_bounded_raw_bytes(self):
        for raw in (b"", b"x" * (MAX_BYTES + 1), "string"):
            with self.subTest(kind=type(raw)), self.assertRaisesRegex(ValueError, "RESPONSE_SIZE"):
                self.parse(raw=raw)

    def test_redirect_or_missing_final_url(self):
        for key in ("url", "sourceURL"):
            for value in (None, "https://other.example/news", self.url + "/"):
                obj = copy.deepcopy(self.obj)
                obj["data"]["metadata"][key] = value
                with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, "SOURCE_URL"):
                    self.parse(obj)

    def test_target_http_status(self):
        for status in (True, None, 403, 429, "200"):
            obj = copy.deepcopy(self.obj)
            obj["data"]["metadata"]["statusCode"] = status
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "HTTP_STATUS"):
                self.parse(obj)

    def test_warning_and_metadata_error(self):
        for field in ("warning", "error"):
            obj = copy.deepcopy(self.obj)
            target = obj["data"] if field == "warning" else obj["data"]["metadata"]
            target[field] = "synthetic error"
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.parse(obj)

    def test_empty_or_invalid_markdown(self):
        for md in ("", " ", None, 1, "\ud800"):
            obj = copy.deepcopy(self.obj)
            obj["data"]["markdown"] = md
            with self.subTest(md=md), self.assertRaises(ValueError):
                self.parse(obj)

    def test_metadata_clock_cannot_promote(self):
        obj = copy.deepcopy(self.obj)
        obj["data"]["metadata"].update(observedAt=self.kw["collected_at"],
                                       publishedTime=self.kw["collected_at"],
                                       independently_verified=True)
        result = self.parse(obj)
        self.assertIsNone(result["upstream_observed_at"])
        self.assertFalse(result["eligible_for_model_scoring"])

    def test_reviewed_url_and_clock_still_required(self):
        with self.assertRaises(ValueError):
            self.parse(reviewed_urls={"https://other.example/news"})
        with self.assertRaises(ValueError):
            self.parse(collected_at="2026-11-24T08:00:00Z")


if __name__ == "__main__":
    unittest.main()
