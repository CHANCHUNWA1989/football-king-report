"""Synthetic GitHub CLI attestation-output contract tests (NOT real crypto).

Mock stdout is never real proof. Every real successful witness requires gh
attestation verify with GitHub signer identity and Rekor Tlog checked fresh.
"""
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vnext_prospective_local_seal import seal_forecast_pair
from vnext_forecast_attestation_gate import (
    REPO, SIGNER_WORKFLOW, SCHEMA, _pinned_cert, audit_witness, verify_witness,
)

KO = "2026-08-01T20:00:00Z"
ASOF = "2026-08-01T18:30:00Z"
NOW = "2026-08-01T18:30:15Z"
CHECKED = "2026-08-01T19:00:00Z"
SOURCE = "a" * 40
WORKFLOW = "b" * 40
RUN_ID = 12345
ATTEMPT = 1


def forecast():
    return {
        "fixture_id": "fixture-pr07-001", "kickoff_utc": KO, "as_of_utc": ASOF,
        "models": {
            side: {
                "model_id": "frozen-" + side,
                "forecast_utc": ASOF,
                "inputs_available_utc": "2026-08-01T18:24:00Z",
                "input_sha256": "a" * 64 if side == "baseline" else "b" * 64,
                "probabilities_1x2": [.45, .30, .25],
                "calibrated": False, "production_recommendations": "DISABLED",
            } for side in ("baseline", "challenger")
        },
    }


def refs():
    return [{
        "provider": "synthetic-provider", "source_event_id": "event-001",
        "source_group": "upstream-not-authenticated",
        "source_updated_utc": "2026-08-01T18:20:00Z",
        "received_utc": "2026-08-01T18:22:00Z",
        "available_utc": "2026-08-01T18:23:00Z",
        "raw_sha256": "c" * 64,
        "rights_scope": "DERIVED_METADATA_ONLY_UNVERIFIED",
    }]


class WitnessFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.seal = seal_forecast_pair(self.root, forecast(), refs(), captured_utc=NOW)
        self.bundle = {"mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
                       "verificationMaterial": {"synthetic": True}}
        self.bundle_path = self.root / "bundle.json"
        self.bundle_path.write_text(json.dumps(self.bundle), encoding="utf-8")
        self.output = self.faux_verified()
        self.kwargs = {
            "expected_sha256": self.seal["content_sha256"],
            "bundle_path": self.bundle_path,
            "source_commit": SOURCE, "workflow_commit": WORKFLOW,
            "run_id": RUN_ID, "attempt": ATTEMPT, "checked_utc": CHECKED,
        }

    def faux_verified(self):
        return [{
            "attestation": {"bundle": self.bundle},
            "verificationResult": {
                "mediaType": "application/vnd.dev.sigstore.verificationresult+json;version=0.1",
                "signature": {"certificate": _pinned_cert(SOURCE, WORKFLOW, RUN_ID, ATTEMPT)},
                "verifiedTimestamps": [{
                    "type": "Tlog", "uri": "https://rekor.sigstore.dev",
                    "timestamp": "2026-08-01T18:33:00Z",
                }],
                "statement": {
                    "_type": "https://in-toto.io/Statement/v1",
                    "predicateType": "https://slsa.dev/provenance/v1",
                    "subject": [{
                        "name": self.seal["file_name"],
                        "digest": {"sha256": self.seal["content_sha256"]},
                    }],
                    "predicate": {"synthetic": True},
                },
            },
        }]

    def _mocked(self, *, output=None, status=0):
        data = self.output if output is None else output
        return patch(
            "vnext_forecast_attestation_gate.subprocess.run",
            return_value=SimpleNamespace(
                returncode=status,
                stdout=json.dumps(data).encode("utf-8"),
                stderr=b"synthetic mocked stdout"),
        )

    def verify(self, *, output=None, status=0):
        with self._mocked(output=output, status=status):
            return audit_witness(self.root, self.seal["file_name"], **self.kwargs)


class WitnessContractTests(WitnessFixture):
    def test_faux_verifier_success_only_authenticates_seal_bytes(self):
        result = self.verify()
        self.assertEqual(result["status"], "WITNESSED_BYTES_RESEARCH")
        self.assertTrue(result["signed_seal_bytes_verified"])
        self.assertTrue(result["external_forecast_time_witness_verified"])
        self.assertEqual(result["fixture_id"], "fixture-pr07-001")
        self.assertEqual(result["subject_sha256"], self.seal["content_sha256"])
        self.assertFalse(result["result_truth_verified"])
        self.assertFalse(result["source_license_verified"])
        self.assertFalse(result["source_independence_verified"])
        self.assertFalse(result["model_scoring_eligible"])
        self.assertFalse(result["positive_ev_verified"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_cli_arguments_pin_signer_run_and_sha_no_shell(self):
        with patch("vnext_forecast_attestation_gate.subprocess.run", return_value=SimpleNamespace(
                returncode=0, stdout=json.dumps(self.output).encode(), stderr=b"")) as called:
            verify_witness(self.root, self.seal["file_name"], **self.kwargs)
        args = called.call_args.args[0]
        self.assertEqual(args[:3], ["gh", "attestation", "verify"])
        self.assertIn("--source-ref", args)
        self.assertEqual(args[args.index("--source-ref") + 1], "refs/heads/main")
        self.assertEqual(args[args.index("--source-digest") + 1], SOURCE)
        self.assertEqual(args[args.index("--signer-digest") + 1], WORKFLOW)
        self.assertEqual(args[args.index("--signer-workflow") + 1],
                         REPO + "/" + SIGNER_WORKFLOW)
        self.assertIn("--deny-self-hosted-runners", args)
        self.assertFalse(called.call_args.kwargs["shell"])

    def test_missing_real_cli_does_not_fallback_to_saved_verified_json(self):
        with patch("vnext_forecast_attestation_gate.subprocess.run", side_effect=OSError("gh absent")):
            output = audit_witness(self.root, self.seal["file_name"], **self.kwargs)
        self.assertEqual(output["status"], "HOLD")
        self.assertEqual(output["reason"], "GH_VERIFIER_UNAVAILABLE_OR_TIMEOUT")

    def test_nonzero_gh_exit_fails(self):
        self.assertEqual(self.verify(status=1)["reason"], "GH_ATTESTATION_VERIFICATION_FAILED")

    def test_bundle_mismatch_fails(self):
        output = copy.deepcopy(self.output)
        output[0]["attestation"]["bundle"]["mediaType"] = "other"
        self.assertEqual(self.verify(output=output)["reason"], "VERIFIED_BUNDLE_MISMATCH")

    def test_forged_signer_or_wrong_workflow_ref_fails(self):
        for key, value in (("subjectAlternativeName", "https://evil.invalid/sign"),
                           ("githubWorkflowRef", "refs/heads/evil"),
                           ("runnerEnvironment", "self-hosted"),
                           ("sourceRepositoryDigest", "c" * 40)):
            with self.subTest(key=key):
                output = copy.deepcopy(self.output)
                output[0]["verificationResult"]["signature"]["certificate"][key] = value
                self.assertEqual(self.verify(output=output)["reason"],
                                 "SIGNER_CERTIFICATE_IDENTITY_MISMATCH")

    def test_wrong_subject_name_or_hash_fails(self):
        for key, value in (("name", "different.json"), ("digest", {"sha256": "f" * 64})):
            with self.subTest(key=key):
                output = copy.deepcopy(self.output)
                output[0]["verificationResult"]["statement"]["subject"][0][key] = value
                self.assertEqual(self.verify(output=output)["reason"],
                                 "SIGNED_SUBJECT_NAME_OR_HASH_MISMATCH")

    def test_two_subjects_or_multiple_verifications_not_accepted(self):
        output = copy.deepcopy(self.output)
        output[0]["verificationResult"]["statement"]["subject"].append(
            copy.deepcopy(output[0]["verificationResult"]["statement"]["subject"][0]))
        self.assertEqual(self.verify(output=output)["status"], "HOLD")
        self.assertEqual(self.verify(output=self.output * 2)["reason"],
                         "AMBIGUOUS_VERIFICATION_OUTPUT")

    def test_rekor_time_after_kickoff_cutoff_holds(self):
        output = copy.deepcopy(self.output)
        output[0]["verificationResult"]["verifiedTimestamps"][0]["timestamp"] = (
            "2026-08-01T19:55:00Z")
        # Evaluate after this claimed witness so we test the *kickoff cutoff*
        # rather than the separate future-witness-time safety check.
        self.kwargs["checked_utc"] = "2026-08-01T21:00:00Z"
        self.assertEqual(self.verify(output=output)["reason"],
                         "WITNESS_AFTER_PREMATCH_CUTOFF_OR_BEFORE_CAPTURE")

    def test_rekor_time_before_claimed_capture_holds(self):
        output = copy.deepcopy(self.output)
        output[0]["verificationResult"]["verifiedTimestamps"][0]["timestamp"] = (
            "2026-08-01T18:29:00Z")
        self.assertEqual(self.verify(output=output)["reason"],
                         "WITNESS_AFTER_PREMATCH_CUTOFF_OR_BEFORE_CAPTURE")

    def test_wrong_transparency_log_uri_or_missing_timestamp_holds(self):
        output = copy.deepcopy(self.output)
        output[0]["verificationResult"]["verifiedTimestamps"][0]["uri"] = "https://false.test"
        self.assertEqual(self.verify(output=output)["reason"], "WRONG_TRANSPARENCY_WITNESS")
        output = copy.deepcopy(self.output)
        output[0]["verificationResult"]["verifiedTimestamps"] = []
        self.assertEqual(self.verify(output=output)["reason"],
                         "NO_SINGLE_VERIFIED_TRANSPARENCY_WITNESS")

    def test_future_verified_witness_holds(self):
        output = copy.deepcopy(self.output)
        output[0]["verificationResult"]["verifiedTimestamps"][0]["timestamp"] = (
            "2026-08-02T09:00:00Z")
        self.assertEqual(self.verify(output=output)["reason"],
                         "FUTURE_OR_UNTRUSTED_WITNESS_TIME")

    def test_wrong_predicate_type_holds(self):
        output = copy.deepcopy(self.output)
        output[0]["verificationResult"]["statement"]["predicateType"] = "fake"
        self.assertEqual(self.verify(output=output)["reason"],
                         "INVALID_VERIFIED_PREDICATE_TYPE")

    def test_wrong_bundle_file_or_digest_never_promotes(self):
        kwargs = dict(self.kwargs)
        kwargs["expected_sha256"] = "0" * 64
        with self._mocked():
            result = audit_witness(self.root, self.seal["file_name"], **kwargs)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "ARCHIVE_INTEGRITY_OR_SIZE_FAILURE")

    def test_malformed_run_id_commit_or_attempt_holds(self):
        for change in ({"source_commit": "not-sha"},
                       {"run_id": True}, {"attempt": 0},
                       {"workflow_commit": "0" * 39}):
            with self.subTest(change=change):
                kwargs = dict(self.kwargs)
                kwargs.update(change)
                with self._mocked():
                    response = audit_witness(self.root, self.seal["file_name"], **kwargs)
                self.assertEqual(response["reason"], "INVALID_PINNED_VERIFICATION_CONTEXT")

    def test_symlink_bundle_and_duplicate_keys_holds(self):
        symlink = self.root / "link.bundle"
        symlink.symlink_to(self.bundle_path)
        kwargs = dict(self.kwargs)
        kwargs["bundle_path"] = symlink
        with self._mocked():
            result = audit_witness(self.root, self.seal["file_name"], **kwargs)
        self.assertEqual(result["status"], "HOLD")
        self.bundle_path.write_text('{"x":1,"x":2}', encoding="utf-8")
        self.assertEqual(self.verify()["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
