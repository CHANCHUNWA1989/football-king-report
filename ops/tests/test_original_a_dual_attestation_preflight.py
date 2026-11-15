"""Mocked gh stdout policy checks; NEVER cryptographic test certification."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ops.original_a_dual_attestation_preflight import (
    audit, _expected_cert, REPOSITORY, WORKFLOW_PATH,
)
from ops.tests.test_original_a_same_get_shadow_pair import ExactOriginalGetShadowLinkTests

SOURCE = "a" * 40
WORKFLOW = "b" * 40
SOURCE_RUN, LINK_RUN = "100001", "100002"
SOURCE_WITNESS = "2026-11-30T19:47:00Z"
LINK_WITNESS = "2026-11-30T19:55:00Z"
NOW = datetime(2026, 11, 30, 20, 0, tzinfo=timezone.utc)


class DualMainSignerPolicyTests(unittest.TestCase):
    def setUp(self):
        self.original = ExactOriginalGetShadowLinkTests(
            "test_genuine_same_bytes_synthetic_a_fixture_replays_no_certification")
        self.original.setUp()
        self.addCleanup(self.original.doCleanups)
        created = self.original.create()
        self.pair_sha = created["private_link_sha256_unattested"]
        self.source_sha = self.original.private_sha
        self.original_file = self.original.source / (
            self.source_sha + ".openliga-private.tar")
        self.link_file = self.original.link_file(created)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.proof_dir = Path(self.temp.name)
        self.bundle = {
            "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
            "dsseEnvelope": {"payload": "SYNTHETIC_NOT_A_REAL_SIGNATURE"},
        }
        for name in ("source.sigstore.json", "link.sigstore.json"):
            p = self.proof_dir / name
            p.write_text(json.dumps(self.bundle))
            p.chmod(0o600)
        self.first = self.verified(self.original_file, SOURCE_RUN, SOURCE_WITNESS)
        self.second = self.verified(self.link_file, LINK_RUN, LINK_WITNESS)

    def verified(self, path, run, time):
        return [{
            "attestation": {"bundle": copy.deepcopy(self.bundle)},
            "verificationResult": {
                "mediaType":
                    "application/vnd.dev.sigstore.verificationresult+json;version=0.1",
                "signature": {"certificate": _expected_cert(SOURCE, WORKFLOW, run, "1")},
                "verifiedTimestamps": [
                    {"type": "Tlog", "uri": "https://rekor.sigstore.dev",
                     "timestamp": time}
                ],
                "statement": {
                    "_type": "https://in-toto.io/Statement/v1",
                    "predicateType": "https://slsa.dev/provenance/v1",
                    "subject": [{"name": path.name, "digest": {
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}}],
                },
            },
        }]

    def run_check(self, response=None, **revisions):
        opts = {
            "original_dir": self.original.source,
            "pair_file": self.link_file, "proof_dir": self.proof_dir,
            "original_sha": self.source_sha, "pair_sha": self.pair_sha,
            "source_sha": SOURCE, "workflow_sha": WORKFLOW,
            "source_run": SOURCE_RUN, "source_attempt": "1",
            "link_run": LINK_RUN, "link_attempt": "1", "now": NOW,
        }
        opts.update(revisions)
        data = response if response is not None else [self.first, self.second]
        calls = [subprocess.CompletedProcess([], 0, json.dumps(v).encode(), b"")
                 for v in data]
        with patch("ops.original_a_dual_attestation_preflight.subprocess.run",
                   side_effect=calls) as runner:
            result = audit(**opts)
        return result, runner

    def held(self, result):
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["positive_ev_verified"])
        self.assertFalse(result["eligible_for_model_scoring"])
        self.assertEqual(result["certified_prospective_samples"], 0)
        self.assertFalse(result["source_publisher_authenticated"])
        self.assertFalse(result["actual_kickoff_independently_authenticated"])
        self.assertFalse(result["training_data_rights_verified"])
        self.assertFalse(result["model_promoted"])

    def test_both_mocked_main_signatures_are_still_hold_and_unpromoted(self):
        r, run = self.run_check()
        self.held(r)
        self.assertTrue(r["audit_completed"])
        self.assertEqual(r["matched_local_native_fixture_count"], 1)
        self.assertTrue(r["exact_main_signer_identity_and_two_subjects_verified"])
        self.assertTrue(r["fresh_source_rekor_witness_verified"])
        self.assertTrue(r["fresh_a_link_rekor_witness_verified"])
        self.assertEqual(run.call_count, 2)
        for call, subject in zip(run.call_args_list,
                                 [self.original_file, self.link_file]):
            argv = call.args[0]
            self.assertEqual(argv[:3], ["gh", "attestation", "verify"])
            self.assertEqual(argv[3], str(subject))
            self.assertIn("--deny-self-hosted-runners", argv)
            self.assertEqual(argv[argv.index("--source-ref") + 1],
                             "refs/heads/main")
            self.assertEqual(argv[argv.index("--source-digest") + 1], SOURCE)
            self.assertEqual(argv[argv.index("--signer-digest") + 1], WORKFLOW)
            self.assertEqual(argv[argv.index("--signer-workflow") + 1],
                             REPOSITORY + "/" + WORKFLOW_PATH)
            self.assertEqual(call.kwargs["timeout"], 30)
            self.assertFalse(call.kwargs["shell"])
            self.assertNotIn("env", call.kwargs)

    def test_no_raw_bundle_is_not_a_witness(self):
        (self.proof_dir / "source.sigstore.json").unlink()
        r, run = self.run_check()
        self.held(r)
        self.assertFalse(r["audit_completed"])
        run.assert_not_called()

    def test_saved_verification_json_cannot_bypass_no_proof(self):
        (self.proof_dir / "source.sigstore.json").unlink()
        (self.proof_dir / "verification.json").write_text('{"audit_completed":true}')
        r, run = self.run_check()
        self.held(r)
        self.assertFalse(r["audit_completed"])
        run.assert_not_called()

    def test_source_witness_after_recorded_a_is_rejected_before_second_verify(self):
        self.first[0]["verificationResult"]["verifiedTimestamps"][0]["timestamp"] = (
            "2026-11-30T19:51:00Z")
        r, run = self.run_check()
        self.held(r)
        self.assertEqual(r["reason"], "SOURCE_REKOR_NOT_BEFORE_RECORDED_A_COMPLETION")
        self.assertEqual(run.call_count, 1)

    def test_source_witness_before_claimed_capture_rejected(self):
        self.first[0]["verificationResult"]["verifiedTimestamps"][0]["timestamp"] = (
            "2026-11-30T19:40:00Z")
        r, run = self.run_check()
        self.held(r)
        self.assertEqual(r["reason"], "SOURCE_REKOR_NOT_BEFORE_RECORDED_A_COMPLETION")
        self.assertEqual(run.call_count, 1)

    def test_rekor_witness_cannot_precede_private_raw_seal_completion(self):
        # Synthetic local source was sealed at 19:46 UTC but the metadata
        # claims capture at 19:45; a 19:45:30 witness is impossible for it.
        self.first[0]["verificationResult"]["verifiedTimestamps"][0]["timestamp"] = (
            "2026-11-30T19:45:30Z")
        r, run = self.run_check()
        self.held(r)
        self.assertEqual(r["reason"], "SOURCE_REKOR_BEFORE_LOCAL_SOURCE_SEAL")
        self.assertEqual(run.call_count, 1)

    def test_link_witness_later_than_kickoff_buffer_rejected(self):
        self.second[0]["verificationResult"]["verifiedTimestamps"][0]["timestamp"] = (
            "2026-11-30T23:51:00Z")
        # Verification takes place AFTER the simulated kickoff; otherwise
        # the independent future-clock rejection would correctly fire first.
        r, run = self.run_check(
            now=datetime(2026, 12, 1, 1, 0, tzinfo=timezone.utc))
        self.held(r)
        self.assertEqual(r["reason"], "A_LINK_REKOR_NOT_BEFORE_RECORDED_KICKOFF")
        self.assertEqual(run.call_count, 2)

    def test_link_witness_before_a_completion_rejected(self):
        self.second[0]["verificationResult"]["verifiedTimestamps"][0]["timestamp"] = (
            "2026-11-30T19:49:00Z")
        r, run = self.run_check()
        self.held(r)
        self.assertEqual(r["reason"], "A_LINK_REKOR_NOT_BEFORE_RECORDED_KICKOFF")

    def test_single_same_run_cannot_claim_two_distinct_timestamps(self):
        r, run = self.run_check(link_run=SOURCE_RUN)
        self.held(r)
        self.assertEqual(r["reason"], "SAME_RUN_CANNOT_ESTABLISH_SEPARATE_PRIOR_WITNESS")
        run.assert_not_called()

    def test_signature_witness_type_must_be_rekor(self):
        self.second[0]["verificationResult"]["verifiedTimestamps"][0]["type"] = "TSA"
        r, _ = self.run_check()
        self.held(r)
        self.assertEqual(r["reason"], "MISSING_REAL_REKOR_WITNESS")

    def test_signature_witness_uri_must_be_rekor(self):
        self.second[0]["verificationResult"]["verifiedTimestamps"][0]["uri"] = (
            "https://example.test/rekor")
        r, _ = self.run_check()
        self.held(r)
        self.assertEqual(r["reason"], "MISSING_REAL_REKOR_WITNESS")

    def test_non_utc_rekor_witness_format_rejected(self):
        self.second[0]["verificationResult"]["verifiedTimestamps"][0]["timestamp"] = (
            "2026-11-30T20:55:00+01:00")
        r, _ = self.run_check()
        self.held(r)
        self.assertEqual(r["reason"], "NON_UTC_REKOR_WITNESS")

    def test_naive_rekor_witness_rejected(self):
        self.second[0]["verificationResult"]["verifiedTimestamps"][0]["timestamp"] = (
            "2026-11-30T19:55:00")
        r, _ = self.run_check()
        self.held(r)
        self.assertEqual(r["reason"], "NON_UTC_REKOR_WITNESS")

    def test_multiple_witnesses_rejected(self):
        self.first[0]["verificationResult"]["verifiedTimestamps"].append(
            {"type": "Tlog", "uri": "https://rekor.sigstore.dev",
             "timestamp": SOURCE_WITNESS})
        r, _ = self.run_check()
        self.held(r)
        self.assertEqual(r["reason"], "MISSING_REAL_REKOR_WITNESS")

    def test_untrusted_or_wrong_github_workflow_identity_rejected(self):
        self.first[0]["verificationResult"]["signature"]["certificate"][
            "subjectAlternativeName"] = "https://github.com/foreign/action"
        r, _ = self.run_check()
        self.held(r)
        self.assertEqual(r["reason"], "UNAPPROVED_OR_NON_MAIN_SIGNER_IDENTITY")

    def test_forged_non_main_source_ref_rejected(self):
        self.second[0]["verificationResult"]["signature"]["certificate"][
            "githubWorkflowRef"] = "refs/heads/research"
        r, _ = self.run_check()
        self.held(r)
        self.assertEqual(r["reason"], "UNAPPROVED_OR_NON_MAIN_SIGNER_IDENTITY")

    def test_wrong_verified_source_subject_hash_rejected(self):
        self.first[0]["verificationResult"]["statement"]["subject"][0]["digest"] = {
            "sha256": "c" * 64}
        r, _ = self.run_check()
        self.held(r)
        self.assertEqual(r["reason"], "SIGNED_SUBJECT_BYTES_MISMATCH")

    def test_wrong_verified_link_subject_name_rejected(self):
        self.second[0]["verificationResult"]["statement"]["subject"][0]["name"] = (
            "OTHER.tar")
        r, _ = self.run_check()
        self.held(r)
        self.assertEqual(r["reason"], "SIGNED_SUBJECT_BYTES_MISMATCH")

    def test_extra_signed_subject_cannot_be_accepted(self):
        self.second[0]["verificationResult"]["statement"]["subject"].append(
            {"name": "extra", "digest": {"sha256": "d" * 64}})
        r, _ = self.run_check()
        self.held(r)
        self.assertEqual(r["reason"], "SIGNED_SUBJECT_BYTES_MISMATCH")

    def test_attested_bundle_must_equal_retrieved_exact_bundle(self):
        self.second[0]["attestation"]["bundle"] = {"other": True}
        r, _ = self.run_check()
        self.held(r)
        self.assertEqual(r["reason"], "VERIFIED_BUNDLE_NOT_THE_SUPPLIED_BUNDLE")

    def test_duplicate_or_malformed_cli_json_rejected(self):
        bad = subprocess.CompletedProcess([], 0, b'{"x":1,"x":2}', b"")
        with patch("ops.original_a_dual_attestation_preflight.subprocess.run",
                   return_value=bad) as run:
            r = audit(original_dir=self.original.source, pair_file=self.link_file,
                proof_dir=self.proof_dir, original_sha=self.source_sha,
                pair_sha=self.pair_sha, source_sha=SOURCE,
                workflow_sha=WORKFLOW, source_run=SOURCE_RUN,
                source_attempt="1", link_run=LINK_RUN,
                link_attempt="1", now=NOW)
        self.held(r)
        self.assertEqual(r["reason"], "DUPLICATE_PROOF_JSON_KEY")
        self.assertEqual(run.call_count, 1)

    def test_wrong_private_raw_byte_archive_rejected_before_cli(self):
        p = self.original_file
        p.write_bytes(p.read_bytes() + b"x")
        r, run = self.run_check()
        self.held(r)
        self.assertFalse(r["audit_completed"])
        run.assert_not_called()

    def test_missing_attested_pair_file_fails_without_cli(self):
        self.link_file.unlink()
        r, run = self.run_check()
        self.held(r)
        self.assertFalse(r["audit_completed"])
        run.assert_not_called()

    def test_ambiguous_proof_bundle_allowlist_rejected(self):
        x = self.proof_dir / "old-verification.json"
        x.write_text('{"verified":true}')
        r, run = self.run_check()
        self.held(r)
        self.assertEqual(r["reason"], "PROOF_BUNDLE_ALLOWLIST_MISMATCH")
        run.assert_not_called()

    def test_gh_cli_failure_never_used_as_proof(self):
        with patch("ops.original_a_dual_attestation_preflight.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 1, b"[]", b"PRIVATE ERROR")):
            r = audit(original_dir=self.original.source, pair_file=self.link_file,
                proof_dir=self.proof_dir, original_sha=self.source_sha,
                pair_sha=self.pair_sha, source_sha=SOURCE,
                workflow_sha=WORKFLOW, source_run=SOURCE_RUN,
                source_attempt="1", link_run=LINK_RUN,
                link_attempt="1", now=NOW)
        self.held(r)
        self.assertEqual(r["reason"], "ATTESTATION_CLI_REJECTED")
        self.assertNotIn("PRIVATE ERROR", json.dumps(r))

    def test_no_gh_tool_fails_closed(self):
        with patch("ops.original_a_dual_attestation_preflight.subprocess.run",
                   side_effect=FileNotFoundError):
            r = audit(original_dir=self.original.source, pair_file=self.link_file,
                proof_dir=self.proof_dir, original_sha=self.source_sha,
                pair_sha=self.pair_sha, source_sha=SOURCE,
                workflow_sha=WORKFLOW, source_run=SOURCE_RUN,
                source_attempt="1", link_run=LINK_RUN,
                link_attempt="1", now=NOW)
        self.held(r)
        self.assertEqual(r["reason"], "TRUSTED_GH_VERIFY_UNAVAILABLE")

    def test_wrong_preapproved_main_commit_rejected_before_gh(self):
        r, run = self.run_check(source_sha="not-a-sha")
        self.held(r)
        self.assertEqual(r["reason"], "INVALID_TRUSTED_MAIN_COMMIT")
        run.assert_not_called()

    def test_reference_uses_user_provided_main_run_not_wildcard(self):
        r, run = self.run_check(source_run="0")
        self.held(r)
        self.assertEqual(r["reason"], "INVALID_TRUSTED_RUN_ID")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
