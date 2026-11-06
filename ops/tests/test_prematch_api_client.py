"""Offline fault-injection tests for the read-only provider API client."""
import json
import os
import tempfile
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prematch_api_client import fetch_provider_quote


class TestPrematchAPIClient(unittest.TestCase):
    def setUp(self):
        self.fixture = {"fixture_id": "match-1", "home_team_id": "h",
                        "away_team_id": "a", "kickoff_at_utc": "2026-10-24T12:00:00Z"}
        self.document = {"provider_id": "provider-a", "provider_fixture_id": "p-1",
                         "home_team_id": "h", "away_team_id": "a",
                         "kickoff_at_utc": "2026-10-24T12:00:00Z",
                         "captured_at_utc": "2026-10-24T11:00:00Z",
                         "decimal_odds": {"home": 2.0, "draw": 3.5, "away": 4.0}}
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.calls = []
        self.sleeps = []
        self.response = json.dumps(self.document).encode()

    def invoke(self, transport, **overrides):
        args = dict(url="https://api.example.test/odds",
                    api_key_env="FOOTBALL_TEST_ODDS_KEY", fixture=self.fixture,
                    model_version="v1", model_probabilities={
                        "home": 0.55, "draw": 0.25, "away": 0.20},
                    evaluated_at_utc="2026-10-24T11:05:00Z",
                    provider_id="provider-a", transport=transport,
                    sleeper=self.sleeps.append,
                    archive_directory=self.temp.name,
                    allowed_hosts=("api.example.test",))
        args.update(overrides)
        with patch.dict(os.environ, {"FOOTBALL_TEST_ODDS_KEY": "dummy-unit-test-key"}):
            return fetch_provider_quote(**args)

    def transport(self, status=200, body=None, headers=None):
        def fetch(url, key, timeout):
            self.calls.append((url, timeout))
            return status, self.response if body is None else body, headers or {}
        return fetch

    def test_valid_quote_stays_research_only_with_digest(self):
        result = self.invoke(self.transport())
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(len(result["evidence"]["response_sha256"]), 64)
        self.assertFalse(result["evidence"]["authentication_verified"])
        from prematch_raw_archive import replay_response
        archive = result["evidence"]["archive"]
        self.assertEqual(replay_response(archive["path"], expected_sha256=archive["sha256"]), self.response)
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_rate_limit_then_success(self):
        responses = iter([(429, b"", {"Retry-After": "2"}),
                          (200, self.response, {})])
        result = self.invoke(lambda *_: next(responses))
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(self.sleeps, [2])

    def test_retry_exhaustion_holds(self):
        result = self.invoke(self.transport(status=503))
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(self.sleeps, [1, 2])

    def test_timeout_injection_holds(self):
        def timeout(*_):
            self.calls.append(1)
            raise TimeoutError("injected")
        self.assertEqual(self.invoke(timeout)["status"], "HOLD")
        self.assertEqual(len(self.calls), 3)

    def test_no_retry_on_authentication_failure(self):
        result = self.invoke(self.transport(status=401))
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(len(self.calls), 1)

    def test_provider_identity_mismatch_holds(self):
        body = json.dumps({**self.document, "provider_id": "other"}).encode()
        self.assertEqual(self.invoke(self.transport(body=body))["status"], "HOLD")

    def test_invalid_json_and_oversize_hold(self):
        for body in (b"{bad", b"x" * 1_000_001):
            with self.subTest(length=len(body)):
                self.assertEqual(self.invoke(self.transport(body=body))["status"], "HOLD")

    def test_invalid_url_holds(self):
        for url in ("http://api.example.test/odds", "https://user:pass@api.example.test/",
                    "https://api.example.test:444/odds", "https://api.example.test/#fragment"):
            with self.subTest(url=url):
                self.assertEqual(self.invoke(self.transport(), url=url)["status"], "HOLD")

    def test_unapproved_host_holds(self):
        self.assertEqual(self.invoke(self.transport(),
                         url="https://unapproved.example.test/odds")["status"], "HOLD")

    def test_archive_required_holds(self):
        self.assertEqual(self.invoke(self.transport(),
                         archive_directory=None)["reason"], "ARCHIVE_REQUIRED")

    def test_missing_secret_holds(self):
        with patch.dict(os.environ, {}, clear=True):
            result = fetch_provider_quote(
                url="https://api.example.test/odds",
                api_key_env="FOOTBALL_TEST_ODDS_KEY", fixture=self.fixture,
                model_version="v1", model_probabilities={
                    "home": 0.55, "draw": 0.25, "away": 0.20},
                evaluated_at_utc="2026-10-24T11:05:00Z",
                provider_id="provider-a", transport=self.transport(),
                archive_directory=self.temp.name,
                allowed_hosts=("api.example.test",))
        self.assertEqual(result["reason"], "MISSING_API_CREDENTIAL")


if __name__ == "__main__":
    unittest.main()
