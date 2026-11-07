"""Offline adversarial tests for GitHub attestation watchlist witness verifier.

All signatures below are mocked CLI outputs, never real external evidence.
"""
import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from ops.research_watchlist_review import seal_manifest
from ops.watchlist_witness import audit, REPOSITORY, WORKFLOW_PATH

NOW = datetime(2026, 11, 7, 10, 0, tzinfo=timezone.utc)
SOURCE_SHA = "a" * 40
WORKFLOW_SHA = "b" * 40
RUN_ID = "42300001001"
ATTEMPT = "1"


def watchlist():
    return [{
        "selection_id": "first", "fixture_id": "fixture-synthetic",
        "competition": "synthetic", "model_version": "model-research",
        "market": "asian_handicap", "selection": "away", "line": "1.25",
        "decimal_odds": "2.10", "bookmaker": "synthetic-source",
        "quote_updated_at_utc": "2026-11-07T08:00:00Z",
        "captured_at_utc": "2026-11-07T08:01:00Z",
        "registered_at_utc": "2026-11-07T08:02:00Z",
        "kickoff_at_utc": "2026-11-07T11:00:00Z",
        "decision": "PRIORITY_RESEARCH",
    }]


def success_stdout(subject):
    repository_uri = "https://github.com/" + REPOSITORY
    uri = repository_uri + "/" + WORKFLOW_PATH + "@refs/heads/main"
    cert = {
        "issuer": "https://token.actions.githubusercontent.com",
        "subjectAlternativeName": uri, "githubWorkflowRepository": REPOSITORY,
        "githubWorkflowRef": "refs/heads/main", "githubWorkflowSHA": WORKFLOW_SHA,
        "sourceRepositoryURI": repository_uri, "sourceRepositoryDigest": SOURCE_SHA,
        "sourceRepositoryRef": "refs/heads/main", "runnerEnvironment": "github-hosted",
        "buildSignerURI": uri, "buildSignerDigest": WORKFLOW_SHA,
        "runInvocationURI": repository_uri + "/actions/runs/" + RUN_ID +
                            "/attempts/" + ATTEMPT,
    }
    bundle = {"mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json"}
    output = [{
        "attestation": {"bundle": bundle},
        "verificationResult": {
            "mediaType": "application/vnd.dev.sigstore.verificationresult+json;version=0.1",
            "signature": {"certificate": cert},
            "verifiedTimestamps": [{"type": "Tlog",
                                     "uri": "https://rekor.sigstore.dev",
                                     "timestamp": "2026-11-07T08:10:00+00:00"}],
            "statement": {
                "_type": "https://in-toto.io/Statement/v1",
                "predicateType": "https://slsa.dev/provenance/v1",
                "subject": [{
                    "name": "watchlist-manifest-sha256.txt",
                    "digest": {"sha256": hashlib.sha256(subject).hexdigest()},
                }],
            },
        },
    }]
    return output


class WatchlistWitnessTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.watch = watchlist()
        self.pin = seal_manifest(self.watch, issued_at_utc="2026-11-07T08:03:00Z")
        subject = (self.pin["manifest_sha256"] + "\n").encode("ascii")
        (self.root / "watchlist-manifest-sha256.txt").write_bytes(subject)
        (self.root / "watchlist.sigstore.json").write_text(
            json.dumps({"mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json"}),
            encoding="utf-8")
        self.subject = subject
        self.verified = success_stdout(subject)

    def call(self, *, watch=None, pin=None, stdout=None, returncode=0):
        output = self.verified if stdout is None else stdout
        completed = subprocess.CompletedProcess([], returncode, json.dumps(output).encode(), b"")
        with patch("ops.watchlist_witness.subprocess.run", return_value=completed) as run:
            report = audit(
                self.watch if watch is None else watch,
                self.pin if pin is None else pin,
                proof_dir=self.root, source_sha=SOURCE_SHA,
                workflow_sha=WORKFLOW_SHA, run_id=RUN_ID, attempt=ATTEMPT,
                now=NOW,
            )
        return report, run

    def test_verified_witness_only_proves_signed_pre_recorded_kickoff_digest(self):
        report, runner = self.call()
        self.assertEqual(runner.call_count, 1)
        cmd = runner.call_args.args[0]
        self.assertIn("--deny-self-hosted-runners", cmd)
        self.assertIn("--source-digest", cmd)
        self.assertIn("--signer-digest", cmd)
        self.assertTrue(report["signature_subject_and_tlog_verified"])
        self.assertTrue(report["observed_before_recorded_kickoff"])
        self.assertFalse(report["actual_kickoff_independently_authenticated"])
        self.assertFalse(report["bookmaker_quote_source_verified"])
        self.assertFalse(report["eligible_for_betting_promotion"])
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_changed_watchlist_cannot_reuse_signed_subject(self):
        mutated = copy.deepcopy(self.watch)
        mutated[0]["decision"] = "EXCLUDED"
        report, _ = self.call(watch=mutated)
        self.assertFalse(report["signature_subject_and_tlog_verified"])
        self.assertEqual(report["reason"], "WATCHLIST_PIN_MISMATCH")

    def test_subject_replacement_cannot_reuse_bundle(self):
        (self.root / "watchlist-manifest-sha256.txt").write_text("f"*64+"\n")
        report, _ = self.call()
        self.assertFalse(report["signature_subject_and_tlog_verified"])

    def test_bad_cli_signature_is_fail_closed(self):
        report, _ = self.call(returncode=1)
        self.assertFalse(report["signature_subject_and_tlog_verified"])
        self.assertEqual(report["reason"], "ATTESTATION_CLI_REJECTED")

    def test_saved_fake_verified_json_cannot_override_failed_cli(self):
        (self.root / "verification.json").write_text(json.dumps(self.verified))
        report, _ = self.call(returncode=1)
        self.assertFalse(report["signature_subject_and_tlog_verified"])

    def test_certificate_identity_and_subject_mismatch_rejected(self):
        changes = [
            lambda x: x[0]["verificationResult"]["signature"]["certificate"].update(
                sourceRepositoryRef="refs/heads/research"),
            lambda x: x[0]["verificationResult"]["signature"]["certificate"].update(
                githubWorkflowSHA="c"*40),
            lambda x: x[0]["verificationResult"]["signature"]["certificate"].update(
                runnerEnvironment="self-hosted"),
            lambda x: x[0]["verificationResult"]["statement"]["subject"][0].update(
                digest={"sha256": "a"*64}),
            lambda x: x[0]["verificationResult"]["statement"].update(
                predicateType="https://example.invalid/unspecified"),
        ]
        for mutate in changes:
            altered = copy.deepcopy(self.verified)
            mutate(altered)
            with self.subTest(mutate=str(mutate)):
                report, _ = self.call(stdout=altered)
                self.assertFalse(report["signature_subject_and_tlog_verified"])

    def test_trusted_tlog_too_late_for_recorded_kickoff(self):
        altered = copy.deepcopy(self.verified)
        altered[0]["verificationResult"]["verifiedTimestamps"][0][
            "timestamp"] = "2026-11-07T10:55:00Z"
        report, _ = self.call(stdout=altered)
        self.assertTrue(report["signature_subject_and_tlog_verified"])
        self.assertFalse(report["observed_before_recorded_kickoff"])
        self.assertEqual(report["reason"], "WITNESS_TOO_LATE_FOR_RECORDED_KICKOFF")

    def test_tlog_earlier_than_local_pin_creation_rejected(self):
        altered = copy.deepcopy(self.verified)
        altered[0]["verificationResult"]["verifiedTimestamps"][0][
            "timestamp"] = "2026-11-07T08:02:00Z"
        report, _ = self.call(stdout=altered)
        self.assertTrue(report["signature_subject_and_tlog_verified"])
        self.assertFalse(report["observed_before_recorded_kickoff"])
        self.assertEqual(report["reason"], "WITNESS_BEFORE_PIN_ISSUED")

    def test_absent_bundle_or_symlink_subject_fails_closed(self):
        (self.root / "watchlist.sigstore.json").unlink()
        report, run = self.call()
        self.assertFalse(report["signature_subject_and_tlog_verified"])
        self.assertEqual(run.call_count, 0)
        (self.root / "watchlist-manifest-sha256.txt").unlink()
        outside = self.root / "other.txt"
        outside.write_bytes(self.subject)
        (self.root / "watchlist-manifest-sha256.txt").symlink_to(outside)
        report, run = self.call()
        self.assertFalse(report["signature_subject_and_tlog_verified"])
        self.assertEqual(run.call_count, 0)

    def test_untrusted_pin_self_claimed_verified_cannot_promote(self):
        pin = {**self.pin, "external_attestation_verified": True}
        report, run = self.call(pin=pin)
        self.assertFalse(report["signature_subject_and_tlog_verified"])
        self.assertEqual(run.call_count, 0)

    def test_output_no_real_attestation_without_cli(self):
        with patch("ops.watchlist_witness.subprocess.run", side_effect=FileNotFoundError):
            report = audit(self.watch, self.pin, proof_dir=self.root,
                           source_sha=SOURCE_SHA, workflow_sha=WORKFLOW_SHA,
                           run_id=RUN_ID, attempt=ATTEMPT, now=NOW)
        self.assertEqual(report["status"], "HOLD")
        self.assertFalse(report["signature_subject_and_tlog_verified"])


if __name__ == "__main__":
    unittest.main()
