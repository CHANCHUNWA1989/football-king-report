"""Offline mocks for read-only official GitHub witness/run handoff.

Mocks prove policy enforcement ONLY: they are not real Sigstore proofs.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from private_quote_official_run_gate import (
    _fetch_official_run, validate_official_run, audit_official_run,
    OfficialRunError, BASE_URL,
)
from private_quote_seal_attestation import WORKFLOW_PATH, REPOSITORY

RUN = "30000012345"
ATTEMPT = "1"
SHA = "a" * 40
NOW = datetime(2026, 11, 2, 7, 0, tzinfo=timezone.utc)
WITNESS = "2026-11-02T05:02:00+00:00"


def github_success():
    return {
        "id": int(RUN), "run_attempt": 1,
        "event": "workflow_dispatch", "head_branch": "main",
        "status": "completed", "conclusion": "success",
        "head_sha": SHA, "path": WORKFLOW_PATH,
        "created_at": "2026-11-02T05:01:01Z",
        "run_started_at": "2026-11-02T05:01:15Z",
        "updated_at": "2026-11-02T05:05:01Z",
        "repository": {"id": 1411226578, "full_name": REPOSITORY},
        "head_repository": {"id": 1411226578, "full_name": REPOSITORY},
    }


def sealed_success():
    return {
        "signature_and_subject_verified": True,
        "seal_witnessed_before_recorded_kickoff": True,
        "verified_rekor_timestamp_utc": WITNESS,
        "seal_sha256": "c" * 64,
        "status": "HOLD",
        "certified_independent_forward_samples": 0,
        "production_recommendations": "DISABLED",
    }


def call_gate(run=RUN, attempt=ATTEMPT):
    return audit_official_run(Path("/synthetic/nonexistent"),
                              b"not-private-real-odds", {}, {}, {}, b"synthetic",
                              run_id=run, attempt=attempt, now=NOW)


class OfficialReadOnlyRunGateTests(unittest.TestCase):
    def test_metadata_success_pins_main_and_source_sha(self):
        result = validate_official_run(github_success(), run_id=RUN,
                                       attempt=ATTEMPT, now=NOW)
        self.assertEqual(result["source_sha"], SHA)
        self.assertEqual(result["workflow_sha"], SHA)
        self.assertEqual(result["run_id"], RUN)
        self.assertEqual(result["attempt"], ATTEMPT)
        self.assertEqual(result["run_started_utc"].isoformat(),
                         "2026-11-02T05:01:15+00:00")

    def test_only_successful_manual_main_job_with_correct_path_is_eligible(self):
        for name, value in (
            ("event", "pull_request"), ("event", "push"),
            ("head_branch", "feat/private-quote-raw-digest-receipt-20261102"),
            ("head_branch", "feature"),
            ("path", ".github/workflows/four-model-shadow-daily.yml"),
            ("path", ".github/workflows/football-king-iphone.yml"),
            ("status", "in_progress"), ("conclusion", "failure"),
            ("conclusion", None), ("head_sha", "missing"),
            ("run_attempt", 2), ("id", 9876),
        ):
            with self.subTest(field=name, value=value):
                bad = github_success()
                bad[name] = value
                with self.assertRaises(OfficialRunError):
                    validate_official_run(bad, run_id=RUN,
                                          attempt=ATTEMPT, now=NOW)

    def test_fork_and_wrong_repository_identity_rejected(self):
        for key in ("repository", "head_repository"):
            for field, val in (("id", 99), ("full_name", "attacker/repo")):
                with self.subTest(record=key, field=field):
                    bad = github_success()
                    bad[key] = dict(bad[key], **{field: val})
                    with self.assertRaisesRegex(OfficialRunError,
                                                "RUN_FROM_OTHER_REPOSITORY"):
                        validate_official_run(bad, run_id=RUN,
                                              attempt=ATTEMPT, now=NOW)

    def test_attempt_run_id_and_unicode_injections_fail_before_network(self):
        for bad in ("", "0", "001", "-1", "1/../../secrets", "hi", "1?token=x",
                    "12345\n", "9" * 25, None, 1):
            with self.subTest(bad=str(bad)):
                with patch("private_quote_official_run_gate.urllib.request.build_opener") as req:
                    with self.assertRaises(OfficialRunError):
                        _fetch_official_run(bad)
                    req.assert_not_called()

    def test_https_read_only_fixed_host_and_redirect_policy(self):
        data = json.dumps(github_success()).encode()
        class FakeResponse:
            status = 200
            def __init__(self, url):
                self.url = url
            def geturl(self):
                return self.url
            def read(self, size):
                self.requested_read_max = size
                return data[:size]
            def __enter__(self):
                return self
            def __exit__(self, *exc):
                return None

        def pretend_open(request, timeout):
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(request.full_url, BASE_URL + RUN)
            self.assertEqual(timeout, 8)
            self.assertNotIn("api_key", request.full_url)
            self.assertEqual(request.get_header("Accept"), "application/vnd.github+json")
            return FakeResponse(request.full_url)
        with patch("private_quote_official_run_gate.urllib.request.build_opener") as build:
            build.return_value.open.side_effect = pretend_open
            self.assertEqual(_fetch_official_run(RUN), github_success())
            build.assert_called_once()
            self.assertEqual(len(build.call_args.args), 2)

    def test_endpoint_host_redirect_and_large_responses_fail_closed(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.status = 200
        response.geturl.return_value = "https://attacker.example.invalid/spoofed"
        with patch("private_quote_official_run_gate.urllib.request.build_opener") as build:
            build.return_value.open.return_value = response
            with self.assertRaisesRegex(OfficialRunError, "UNTRUSTED_RUN_ENDPOINT"):
                _fetch_official_run(RUN)
        response.geturl.return_value = BASE_URL + RUN
        response.read.return_value = b"x" * 131073
        with patch("private_quote_official_run_gate.urllib.request.build_opener") as build:
            build.return_value.open.return_value = response
            with self.assertRaisesRegex(OfficialRunError, "INVALID_GITHUB_RUN_RESPONSE_SIZE"):
                _fetch_official_run(RUN)

    def test_duplicate_key_and_nonfinite_github_json_rejected(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.status = 200
        response.geturl.return_value = BASE_URL + RUN
        with patch("private_quote_official_run_gate.urllib.request.build_opener") as build:
            build.return_value.open.return_value = response
            for payload in (b'{"id":1,"id":2}', b'{"id":NaN}', b"[]", b"not-json"):
                with self.subTest(payload=payload):
                    response.read.return_value = payload
                    if payload == b"[]":
                        with self.assertRaisesRegex(OfficialRunError,
                                                    "INVALID_GITHUB_RUN_DOCUMENT"):
                            _fetch_official_run(RUN)
                    else:
                        with self.assertRaisesRegex(OfficialRunError,
                                                    "INVALID_GITHUB_RUN_JSON"):
                            _fetch_official_run(RUN)

    def test_missing_or_future_github_run_dates_fail_closed(self):
        for key, value in (
            ("run_started_at", None),
            ("created_at", "2026-11-02T05:02:00Z"),
            ("updated_at", "2026-11-02T04:00:00Z"),
            ("updated_at", "2026-11-02T08:00:00Z"),
            ("created_at", "2026-11-02T05:01:01"),
        ):
            with self.subTest(field=key):
                bad = github_success()
                bad[key] = value
                with self.assertRaisesRegex(OfficialRunError, "INVALID_GITHUB_RUN_CHRONOLOGY"):
                    validate_official_run(bad, run_id=RUN, attempt=ATTEMPT, now=NOW)

    def test_cannot_inherit_actual_repo_unrelated_pr_run_metadata(self):
        # An observed GitHub safety PR run from our own repository is NOT
        # valid signer evidence, even if completed successfully.
        observed = github_success()
        observed.update({
            "id": 41417374980, "run_attempt": 1,
            "event": "pull_request",
            "head_branch": "feat/private-quote-raw-digest-receipt-20261102",
            "path": ".github/workflows/repository-safety-check.yml",
            "head_sha": "1110dedd168e636311bad2ad1e5ed39ed5a27a15",
        })
        with self.assertRaises(OfficialRunError):
            validate_official_run(observed, run_id="41417374980", attempt="1", now=NOW)

    def test_full_handoff_requires_both_live_github_and_rekor_crypto(self):
        with patch("private_quote_official_run_gate._fetch_official_run",
                   return_value=github_success()) as fetch:
            with patch("private_quote_official_run_gate.audit",
                       return_value=sealed_success()) as signature:
                report = call_gate()
        fetch.assert_called_once_with(RUN)
        self.assertEqual(signature.call_args.kwargs["source_sha"], SHA)
        self.assertEqual(signature.call_args.kwargs["workflow_sha"], SHA)
        self.assertEqual(signature.call_args.kwargs["run_id"], RUN)
        self.assertEqual(signature.call_args.kwargs["attempt"], ATTEMPT)
        self.assertEqual(report["status"], "HOLD")
        self.assertTrue(report["official_run_metadata_https_verified"])
        self.assertTrue(report["signature_and_subject_verified"])
        self.assertTrue(report["seal_witnessed_before_recorded_kickoff"])
        self.assertEqual(report["verified_rekor_timestamp_utc"], WITNESS)
        self.assertEqual(report["certified_independent_forward_samples"], 0)
        self.assertFalse(report["bookmaker_quote_independently_authenticated"])
        self.assertFalse(report["eligible_for_betting_promotion"])
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_fake_or_missing_official_source_never_invokes_sigstore_verify(self):
        for body in (None, {}, dict(github_success(), head_branch="attacker"),
                     dict(github_success(), conclusion="failure")):
            with self.subTest(body=str(body)[:45]):
                with patch("private_quote_official_run_gate._fetch_official_run",
                           return_value=body) as fetch:
                    with patch("private_quote_official_run_gate.audit") as signature:
                        report=call_gate()
                self.assertFalse(report["signature_and_subject_verified"])
                self.assertEqual(report["certified_independent_forward_samples"], 0)
                signature.assert_not_called()
        with patch("private_quote_official_run_gate._fetch_official_run",
                   side_effect=OfficialRunError("GITHUB_RUN_UNAVAILABLE")):
            with patch("private_quote_official_run_gate.audit") as signature:
                report=call_gate()
            self.assertEqual(report["reason"], "GITHUB_RUN_UNAVAILABLE")
            self.assertFalse(report["official_run_metadata_https_verified"])
            signature.assert_not_called()

    def test_fake_signature_or_inconsistent_witness_does_not_award_samples(self):
        for proof in (
            {"signature_and_subject_verified": False, "reason": "CRYPTO_VERIFICATION_REJECTED"},
            dict(sealed_success(), verified_rekor_timestamp_utc="2026-11-02T05:00:01Z"),
            dict(sealed_success(), verified_rekor_timestamp_utc="2026-11-02T05:05:40Z"),
        ):
            with self.subTest(proof=str(proof)[:70]):
                with patch("private_quote_official_run_gate._fetch_official_run",
                           return_value=github_success()):
                    with patch("private_quote_official_run_gate.audit", return_value=proof):
                        report=call_gate()
                self.assertFalse(report["seal_witnessed_before_recorded_kickoff"])
                self.assertEqual(report["certified_independent_forward_samples"], 0)
                self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_no_local_user_supplied_run_metadata_documents_or_paid_api(self):
        source = Path(__file__).resolve().parents[1].joinpath(
            "private_quote_official_run_gate.py").read_text()
        self.assertIn("https://api.github.com/repos/", source)
        self.assertIn('method="GET"', source)
        self.assertIn("ssl.create_default_context()", source)
        self.assertIn("completed", source)
        self.assertNotIn("THE_ODDS_API_KEY", source)
        self.assertNotIn("api.the-odds-api.com", source)
        self.assertNotIn("POST", source)
        self.assertIn("certified_independent_forward_samples", source)
        self.assertIn('production_recommendations": "DISABLED"', source)


if __name__ == "__main__":
    unittest.main()
