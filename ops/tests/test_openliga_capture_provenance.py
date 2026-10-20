"""Verifier policy tests; CLI shims are deliberately not cryptographic proof."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from ops.openliga_capture_provenance import audit, main


REPO = "CHANCHUNWA1989/football-king-report"
URI = "https://github.com/" + REPO
WORKFLOW = URI + "/.github/workflows/four-model-shadow-daily.yml@refs/heads/main"
SOURCE, WORKFLOW_SHA, RUN = "1" * 40, "2" * 40, "39133031901"
NOW = datetime(2026, 10, 19, 14, tzinfo=timezone.utc)
WITNESS = "2026-10-19T13:59:00Z"


class OpenLigaCaptureProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.proof = Path(self.temp.name) / "proof"
        self.proof.mkdir()
        self.raw = b"MOCK_TAR_FOR_CRYPTO_POLICY_ISOLATION"
        (self.proof / "openliga-capture.tar").write_bytes(self.raw)
        self.bundle = {"mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
                       "dsseEnvelope": {"payload": "TU9DSw=="}}
        (self.proof / "capture.sigstore.json").write_text(json.dumps(self.bundle))
        self.options = dict(source_sha=SOURCE, workflow_sha=WORKFLOW_SHA,
                            run_id=RUN, attempt="1", now=NOW)
        self.cert = {
            "issuer": "https://token.actions.githubusercontent.com",
            "subjectAlternativeName": WORKFLOW, "buildSignerURI": WORKFLOW,
            "buildConfigURI": WORKFLOW, "githubWorkflowRepository": REPO,
            "githubWorkflowRef": "refs/heads/main", "githubWorkflowSHA": WORKFLOW_SHA,
            "sourceRepositoryURI": URI, "sourceRepositoryDigest": SOURCE,
            "sourceRepositoryRef": "refs/heads/main", "buildSignerDigest": WORKFLOW_SHA,
            "buildConfigDigest": WORKFLOW_SHA, "runnerEnvironment": "github-hosted",
            "sourceRepositoryIdentifier": "1411226578",
            "sourceRepositoryOwnerURI": "https://github.com/CHANCHUNWA1989",
            "sourceRepositoryOwnerIdentifier": "339931460",
            "runInvocationURI": URI + "/actions/runs/" + RUN + "/attempts/1",
        }
        self.summary = {"schema": "football-king-openliga-capture-summary-v1",
                        "status": "HOLD", "production_recommendations": "DISABLED",
                        "controlled_capture_content_verified": True,
                        "origin_chain_scope": "OPENLIGADB_ONLY", "raw_sha256": "3" * 64,
                        "raw_record_count": 1, "private_raw": "NEVER_RETURN"}

    def stdout(self):
        return [{"attestation": {"bundle": copy.deepcopy(self.bundle)}, "verificationResult": {
            "mediaType": "application/vnd.dev.sigstore.verificationresult+json;version=0.1",
            "signature": {"certificate": copy.deepcopy(self.cert)},
            "verifiedTimestamps": [{"type": "Tlog", "uri": "https://rekor.sigstore.dev",
                                     "timestamp": WITNESS}],
            "statement": {"_type": "https://in-toto.io/Statement/v1",
                          "predicateType": "https://slsa.dev/provenance/v1",
                          "subject": [{"name": "openliga-capture.tar", "digest": {
                              "sha256": hashlib.sha256(self.raw).hexdigest()}}],
                          "predicate": {"untrusted_claimed_time": "1999-01-01T00:00:00Z"}},
        }}]

    def run_audit(self, output=None, **options):
        raw = json.dumps(self.stdout() if output is None else output).encode()
        with patch("ops.openliga_capture_provenance.subprocess.run", return_value=
                   subprocess.CompletedProcess([], 0, raw, b"")) as cli, \
             patch("ops.openliga_capture_provenance.validate_capture", return_value=self.summary) as replay:
            result = audit(self.proof, **dict(self.options, **options))
        return result, cli, replay

    def assert_held(self, result, completed=False):
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["production_recommendations"], "DISABLED")
        for key in ("raw_source_identity_authenticated", "publisher_identity_authenticated",
                    "upstream_independence_authenticated", "actual_kickoff_authenticated",
                    "regulation_ft_authenticated", "formal_eligible",
                    "source_identity_independently_authenticated", "outcomes_independently_authenticated",
                    "independently_verified", "eligible_for_model_scoring", "eligible_for_betting_promotion"):
            self.assertIs(result[key], False)
        self.assertIs(result["audit_completed"], completed)
        self.assertIs(result["signature_identity_and_subject_verified"], completed)
        self.assertIs(result["capture_content_replayed"], completed)
        self.assertNotIn("NEVER_RETURN", json.dumps(result))

    def test_fresh_stdout_checks_one_subject_then_replays_original_bytes(self):
        result, cli, replay = self.run_audit()
        self.assert_held(result, True)
        self.assertEqual(cli.call_count, 1)
        argv = cli.call_args.args[0]
        self.assertEqual(argv[:4], ["gh", "attestation", "verify", str(self.proof / "openliga-capture.tar")])
        for key, value in (("--bundle", str(self.proof / "capture.sigstore.json")),
                           ("--repo", REPO), ("--source-ref", "refs/heads/main"),
                           ("--signer-workflow", REPO + "/.github/workflows/four-model-shadow-daily.yml"),
                           ("--source-digest", SOURCE), ("--signer-digest", WORKFLOW_SHA),
                           ("--format", "json")):
            self.assertEqual(argv[argv.index(key) + 1], value)
        self.assertIn("--deny-self-hosted-runners", argv)
        self.assertEqual(cli.call_args.kwargs["timeout"], 30)
        self.assertIs(cli.call_args.kwargs["shell"], False)
        self.assertNotIn("env", cli.call_args.kwargs)
        replay.assert_called_once_with(self.raw, witness=datetime(2026, 10, 19, 13, 59,
                                                                  tzinfo=timezone.utc), now=NOW)
        self.assertEqual(result["capture_summary"]["raw_sha256"], "3" * 64)

    def test_real_subprocess_shim_supplies_fresh_stdout(self):
        bindir = Path(self.temp.name) / "bin"
        bindir.mkdir()
        shim = bindir / "gh"
        shim.write_text("#!" + sys.executable + "\nimport sys\n"
                        "assert sys.argv[1:3] == ['attestation', 'verify']\n"
                        "sys.stdout.write(" + repr(json.dumps(self.stdout())) + ")\n")
        shim.chmod(0o700)
        with patch.dict(os.environ, {"PATH": str(bindir) + os.pathsep + os.environ.get("PATH", "")}), \
             patch("ops.openliga_capture_provenance.validate_capture", return_value=self.summary):
            result = audit(self.proof, **self.options)
        self.assert_held(result, True)

    def test_extra_saved_verification_file_is_rejected_before_cli(self):
        (self.proof / "capture.verification.json").write_text(json.dumps(self.stdout()))
        with patch("ops.openliga_capture_provenance.subprocess.run") as cli, \
             patch("ops.openliga_capture_provenance.validate_capture") as replay:
            result = audit(self.proof, **self.options)
        self.assert_held(result)
        self.assertEqual(result["reason"], "PROOF_FILE_ALLOWLIST_MISMATCH")
        cli.assert_not_called()
        replay.assert_not_called()

    def test_clean_proof_cli_failures_never_use_saved_success_output(self):
        saved = Path(self.temp.name) / "saved-verification.json"
        saved.write_text(json.dumps(self.stdout()))
        cases = ((FileNotFoundError(), "ATTESTATION_TOOL_UNAVAILABLE_OR_TIMEOUT"),
                 (subprocess.TimeoutExpired("gh", 30), "ATTESTATION_TOOL_UNAVAILABLE_OR_TIMEOUT"),
                 (subprocess.CompletedProcess([], 1, b"[]", b"PRIVATE_ERROR"), "ATTESTATION_CLI_REJECTED"),
                 (subprocess.CompletedProcess([], 0, b"", b""), "EMPTY_OR_OVERSIZED_VERIFICATION_OUTPUT"),
                 (subprocess.CompletedProcess([], 0, b"not-json", b""), "INVALID_JSON"))
        for error, reason in cases:
            with self.subTest(error=type(error).__name__, reason=reason):
                kw = {"side_effect": error} if isinstance(error, Exception) else {"return_value": error}
                with patch("ops.openliga_capture_provenance.subprocess.run", **kw) as cli, \
                     patch("ops.openliga_capture_provenance.validate_capture") as replay:
                    result = audit(self.proof, **self.options)
                self.assert_held(result)
                self.assertEqual(result["reason"], reason)
                self.assertNotIn("PRIVATE_ERROR", json.dumps(result))
                cli.assert_called_once()
                replay.assert_not_called()

    def test_actual_missing_gh_executable_fails_closed(self):
        bindir = Path(self.temp.name) / "empty-bin"
        bindir.mkdir()
        with patch.dict(os.environ, {"PATH": str(bindir)}), \
             patch("ops.openliga_capture_provenance.validate_capture") as replay:
            result = audit(self.proof, **self.options)
        self.assert_held(result)
        self.assertEqual(result["reason"], "ATTESTATION_TOOL_UNAVAILABLE_OR_TIMEOUT")
        replay.assert_not_called()

    def test_every_certificate_identity_field_is_pinned(self):
        for field in self.cert:
            for invalid in ("wrong", None, [self.cert[field]]):
                with self.subTest(field=field, invalid=invalid):
                    output = self.stdout()
                    output[0]["verificationResult"]["signature"]["certificate"][field] = invalid
                    result, _, replay = self.run_audit(output)
                    self.assert_held(result)
                    replay.assert_not_called()

    def test_verification_bundle_statement_subject_and_time_are_unambiguous(self):
        cases = ("no_result", "two_results", "wrong_bundle", "bad_media", "bad_signature", "bad_type",
                 "bad_predicate", "zero_subject", "two_subjects", "path_subject", "wrong_sha",
                 "extra_digest", "zero_timestamps", "two_timestamps", "wrong_tlog", "wrong_uri",
                 "naive_time", "nonutc_time", "future_time")
        for kind in cases:
            with self.subTest(kind=kind):
                output = self.stdout()
                result = output[0]["verificationResult"]
                subject, stamp = result["statement"]["subject"][0], result["verifiedTimestamps"][0]
                if kind == "no_result": output = []
                elif kind == "two_results": output *= 2
                elif kind == "wrong_bundle": output[0]["attestation"]["bundle"] = {}
                elif kind == "bad_media": result["mediaType"] = "wrong"
                elif kind == "bad_signature": result["signature"] = []
                elif kind == "bad_type": result["statement"]["_type"] = "wrong"
                elif kind == "bad_predicate": result["statement"]["predicateType"] = "wrong"
                elif kind == "zero_subject": result["statement"]["subject"] = []
                elif kind == "two_subjects": result["statement"]["subject"] *= 2
                elif kind == "path_subject": subject["name"] = "proof/openliga-capture.tar"
                elif kind == "wrong_sha": subject["digest"]["sha256"] = "0" * 64
                elif kind == "extra_digest": subject["digest"]["sha512"] = "0" * 128
                elif kind == "zero_timestamps": result["verifiedTimestamps"] = []
                elif kind == "two_timestamps": result["verifiedTimestamps"] *= 2
                elif kind == "wrong_tlog": stamp["type"] = "RFC3161"
                elif kind == "wrong_uri": stamp["uri"] = "https://evil.example"
                elif kind == "naive_time": stamp["timestamp"] = "2026-10-19T13:59:00"
                elif kind == "nonutc_time": stamp["timestamp"] = "2026-10-19T14:59:00+01:00"
                elif kind == "future_time": stamp["timestamp"] = "2026-10-19T14:05:01Z"
                report, _, replay = self.run_audit(output)
                self.assert_held(report)
                replay.assert_not_called()

    def test_trusted_caller_arguments_are_validated(self):
        for key, bad in (("source_sha", "f" * 39), ("workflow_sha", "F" * 40),
                         ("source_sha", SOURCE + ";echo nope"), ("run_id", "0"),
                         ("attempt", "01"), ("run_id", 123), ("attempt", "1;id"),
                         ("now", datetime(2026, 10, 19))):
            with self.subTest(key=key, bad=bad):
                result, cli, replay = self.run_audit(**{key: bad})
                self.assert_held(result)
                cli.assert_not_called()
                replay.assert_not_called()

    def test_verified_log_clock_has_no_future_grace(self):
        output = self.stdout()
        output[0]["verificationResult"]["verifiedTimestamps"][0]["timestamp"] = "2026-10-19T14:00:00Z"
        result, _, _ = self.run_audit(output)
        self.assert_held(result, True)
        output[0]["verificationResult"]["verifiedTimestamps"][0]["timestamp"] = "2026-10-19T14:00:00.000001Z"
        result, _, replay = self.run_audit(output)
        self.assert_held(result)
        replay.assert_not_called()

    def test_malformed_sigstore_bytes_and_duplicate_json_are_rejected(self):
        path = self.proof / "capture.sigstore.json"
        for raw in (b"{", b"[]", b'{"mediaType":"x","mediaType":"y"}',
                    b'{"mediaType":NaN}', b"\xff"):
            with self.subTest(raw=raw):
                path.write_bytes(raw)
                result, _, replay = self.run_audit()
                self.assert_held(result)
                replay.assert_not_called()

    def test_tampered_source_bytes_do_not_match_verified_subject(self):
        output = self.stdout()
        (self.proof / "openliga-capture.tar").write_bytes(self.raw + b"tamper")
        result, _, replay = self.run_audit(output)
        self.assert_held(result)
        replay.assert_not_called()

    def test_original_tar_and_bundle_are_reread_after_cli(self):
        for filename in ("openliga-capture.tar", "capture.sigstore.json"):
            with self.subTest(filename=filename):
                path = self.proof / filename
                original = path.read_bytes()
                output = json.dumps(self.stdout()).encode()
                def changed(*args, **kwargs):
                    path.write_bytes(original + b" ")
                    return subprocess.CompletedProcess([], 0, output, b"")
                with patch("ops.openliga_capture_provenance.subprocess.run", side_effect=changed), \
                     patch("ops.openliga_capture_provenance.validate_capture") as replay:
                    result = audit(self.proof, **self.options)
                self.assert_held(result)
                self.assertEqual(result["reason"], "PROOF_BYTES_CHANGED_DURING_VERIFICATION")
                replay.assert_not_called()
                path.write_bytes(original)

    def test_tar_content_failure_fails_closed_even_after_valid_signature(self):
        with patch("ops.openliga_capture_provenance.subprocess.run", return_value=
                   subprocess.CompletedProcess([], 0, json.dumps(self.stdout()).encode(), b"")), \
             patch("ops.openliga_capture_provenance.validate_capture", side_effect=ValueError("PRIVATE_RAW")):
            result = audit(self.proof, **self.options)
        self.assert_held(result)
        self.assertEqual(result["reason"], "CAPTURE_CONTENT_REPLAY_FAILED")
        self.assertNotIn("PRIVATE_RAW", json.dumps(result))

    def test_real_capture_replays_original_openliga_receipts_and_foreign_subject_rejected(self):
        from ops.openliga_capture_pack import prepare
        from ops.tests import test_openliga_capture_pack as pack_tests
        for other_error in (False, True):
            with self.subTest(other_error=other_error):
                raw_dir = Path(self.temp.name) / str(other_error)
                manifest = pack_tests.fixture(raw_dir, other_error=other_error)
                target = self.proof / "openliga-capture.tar"
                target.unlink()
                current = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
                prepare(raw_dir, target, now=current)
                self.raw = target.read_bytes()
                output = self.stdout()
                output[0]["verificationResult"]["verifiedTimestamps"][0]["timestamp"] = "2026-10-20T11:59:00Z"
                with patch("ops.openliga_capture_provenance.subprocess.run", return_value=
                           subprocess.CompletedProcess([], 0, json.dumps(output).encode(), b"")):
                    result = audit(self.proof, **dict(self.options, now=current))
                self.assert_held(result, True)
                self.assertEqual(result["capture_summary"]["raw_sha256"], manifest["sources"][0]["raw_sha256"])
                self.assertEqual(result["capture_summary"]["source_receipt"], manifest["sources"][0])
                self.assertEqual(result["capture_summary"]["origin_chain_scope"], "OPENLIGADB_ONLY")
                output[0]["verificationResult"]["statement"]["subject"][0]["name"] = "ndr-capture.tar"
                with patch("ops.openliga_capture_provenance.subprocess.run", return_value=
                           subprocess.CompletedProcess([], 0, json.dumps(output).encode(), b"")):
                    result = audit(self.proof, **dict(self.options, now=current))
                self.assert_held(result)
                self.assertEqual(result["reason"], "VERIFIED_SUBJECT_BYTES_MISMATCH")

    def test_unsafe_input_aliases_are_rejected(self):
        alias = Path(self.temp.name) / "alias"
        alias.symlink_to(self.proof, target_is_directory=True)
        with patch("ops.openliga_capture_provenance.subprocess.run") as cli:
            self.assert_held(audit(alias, **self.options))
            self.assert_held(audit(alias / ".." / "proof", **self.options))
        cli.assert_not_called()
        for kind in ("symlink", "hardlink"):
            with self.subTest(kind=kind):
                tar = self.proof / "openliga-capture.tar"
                other = Path(self.temp.name) / "original"
                tar.rename(other)
                if kind == "symlink": tar.symlink_to(other)
                else: os.link(other, tar)
                result, cli, replay = self.run_audit()
                self.assert_held(result)
                cli.assert_not_called()
                replay.assert_not_called()
                tar.unlink()
                other.rename(tar)
        tar = self.proof / "openliga-capture.tar"
        tar.unlink()
        os.mkfifo(tar)
        result, cli, replay = self.run_audit()
        self.assert_held(result)
        cli.assert_not_called()
        replay.assert_not_called()

    def test_cli_report_output_cannot_overwrite_or_alias_proof(self):
        args = ["--proof", str(self.proof), "--source-sha", SOURCE, "--workflow-sha", WORKFLOW_SHA,
                "--run-id", RUN, "--attempt", "1", "--output"]
        link = Path(self.temp.name) / "link.json"
        link.symlink_to(self.proof / "capture.sigstore.json")
        hard = Path(self.temp.name) / "hard.json"
        os.link(self.proof / "openliga-capture.tar", hard)
        fifo = Path(self.temp.name) / "fifo.json"
        os.mkfifo(fifo)
        for output in (self.proof / "report.json", self.proof / "openliga-capture.tar", link, hard, fifo):
            with self.subTest(output=output), patch("sys.stderr"):
                with self.assertRaises(SystemExit):
                    main(args + [str(output)])
        hard.unlink()
        destination = Path(self.temp.name) / "report.json"
        for completed in (False, True):
            with patch("ops.openliga_capture_provenance.audit", return_value={"audit_completed": completed}):
                self.assertEqual(main(args + [str(destination)]), 0 if completed else 1)
            self.assertEqual(json.loads(destination.read_text()), {"audit_completed": completed})


if __name__ == "__main__":
    unittest.main()
