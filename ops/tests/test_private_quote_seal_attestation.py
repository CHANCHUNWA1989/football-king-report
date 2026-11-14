"""Synthetic Sigstore-result tests; no gh calls or paid market requests."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_private_quote_forward_freeze import inputs, encode
from private_quote_forward_freeze import freeze
from private_quote_seal_attestation import (
    _certificate, audit, main, REPOSITORY, WORKFLOW_PATH,
)

SOURCE = "a" * 40
WORKFLOW = "b" * 40
RUN = "12345"
ATTEMPT = "1"
NOW = datetime(2026, 11, 2, 7, 0, tzinfo=timezone.utc)
GOOD_WITNESS = "2026-11-02T05:02:00Z"


def evidence():
    raw, receipt, fixture, market, forecast = inputs()
    model = encode(forecast)
    seal = freeze(raw, receipt, fixture, market, model)
    return raw, receipt, fixture, market, model, seal


def make_proof(directory, seal):
    root = Path(directory)
    proof = root / "private-proof"
    proof.mkdir()
    bundle = {
        "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
        "dsseEnvelope": {"payload": "only-synthetic-tests", "signatures": []},
    }
    raw_seal = (json.dumps(seal, sort_keys=True) + "\n").encode()
    (proof / "seal.json").write_bytes(raw_seal)
    (proof / "seal.sigstore.json").write_text(json.dumps(bundle))
    return proof, bundle, raw_seal


def verified_output(bundle, seal_raw, *, stamp=GOOD_WITNESS, cert=None, subject=None):
    expected = _certificate(SOURCE, WORKFLOW, RUN, ATTEMPT)
    identity = expected if cert is None else cert
    default_subject = [{"name": "seal.json",
                        "digest": {"sha256": hashlib.sha256(seal_raw).hexdigest()}}]
    return [{
        "attestation": {"bundle": bundle},
        "verificationResult": {
            "mediaType": "application/vnd.dev.sigstore.verificationresult+json;version=0.1",
            "signature": {"certificate": identity},
            "verifiedTimestamps": [
                {"type": "Tlog", "uri": "https://rekor.sigstore.dev", "timestamp": stamp},
            ],
            "statement": {
                "_type": "https://in-toto.io/Statement/v1",
                "predicateType": "https://slsa.dev/provenance/v1",
                "subject": default_subject if subject is None else subject,
            },
        },
    }]


def mocked_cli(payload, *, code=0):
    return patch("private_quote_seal_attestation.subprocess.run",
                 return_value=SimpleNamespace(
                     returncode=code, stdout=json.dumps(payload).encode(),
                     stderr=b"TEST ONLY"))


def verify(proof, case, **pins):
    raw, receipt, fixture, market, model, _ = case
    return audit(proof, raw, receipt, fixture, market, model,
                 source_sha=pins.get("source_sha", SOURCE),
                 workflow_sha=pins.get("workflow_sha", WORKFLOW),
                 run_id=pins.get("run_id", RUN),
                 attempt=pins.get("attempt", ATTEMPT),
                 now=pins.get("now", NOW))


class PrivateSealSigstoreWitnessTests(unittest.TestCase):
    def test_valid_cryptographic_result_witnesses_only_recorded_kickoff(self):
        case = evidence()
        with tempfile.TemporaryDirectory() as directory:
            proof, bundle, raw_seal = make_proof(directory, case[-1])
            with mocked_cli(verified_output(bundle, raw_seal)) as gh:
                result = verify(proof, case)
            self.assertEqual(result["status"], "HOLD")
            self.assertTrue(result["signature_and_subject_verified"])
            self.assertTrue(result["seal_semantics_replayed"])
            self.assertTrue(result["seal_witnessed_before_recorded_kickoff"])
            self.assertFalse(result["recorded_fixture_kickoff_independently_authenticated"])
            self.assertFalse(result["bookmaker_quote_independently_authenticated"])
            self.assertFalse(result["model_leakage_or_calibration_verified"])
            self.assertEqual(result["certified_independent_forward_samples"], 0)
            self.assertFalse(result["eligible_for_model_scoring"])
            self.assertFalse(result["eligible_for_betting_promotion"])
            self.assertEqual(result["production_recommendations"], "DISABLED")
            self.assertEqual(result["verified_rekor_timestamp_utc"], "2026-11-02T05:02:00+00:00")
            args = gh.call_args.args[0]
            self.assertEqual(args[:3], ["gh", "attestation", "verify"])
            self.assertIn("--deny-self-hosted-runners", args)
            self.assertEqual(args[args.index("--repo")+1], REPOSITORY)
            self.assertEqual(args[args.index("--signer-workflow")+1],
                             REPOSITORY + "/" + WORKFLOW_PATH)
            self.assertEqual(args[args.index("--source-digest")+1], SOURCE)
            self.assertEqual(args[args.index("--signer-digest")+1], WORKFLOW)
            self.assertFalse(gh.call_args.kwargs["shell"])
            self.assertEqual(gh.call_args.kwargs["timeout"], 30)
            report = json.dumps(result)
            for secret in ("private-native-event-1", "synthetic-private-book",
                           "Private Home", "Private Away", "1.9587", "1.9183"):
                self.assertNotIn(secret, report)

    def test_missing_bundle_and_added_fake_verification_report_rejected_without_gh(self):
        case = evidence()
        with tempfile.TemporaryDirectory() as directory:
            proof, _, _ = make_proof(directory, case[-1])
            with patch("private_quote_seal_attestation.subprocess.run") as gh:
                (proof / "fake-verification.json").write_text('{"signed":true}')
                denied = verify(proof, case)
                self.assertEqual(denied["reason"], "MISSING_OR_EXTRA_PROOF_FILES")
                self.assertFalse(denied["signature_and_subject_verified"])
                (proof / "fake-verification.json").unlink()
                (proof / "seal.sigstore.json").unlink()
                denied = verify(proof, case)
                self.assertEqual(denied["reason"], "MISSING_OR_EXTRA_PROOF_FILES")
                gh.assert_not_called()

    def test_wrong_trusted_pins_rejected_even_when_mocked_gh_says_success(self):
        case = evidence()
        with tempfile.TemporaryDirectory() as directory:
            proof, bundle, seal_raw = make_proof(directory, case[-1])
            fake = verified_output(bundle, seal_raw)
            with mocked_cli(fake):
                self.assertEqual(verify(proof, case, source_sha="bad")["reason"],
                                 "INVALID_PINNED_COMMIT")
                self.assertEqual(verify(proof, case, run_id="1.2")["reason"],
                                 "INVALID_PINNED_RUN")
                self.assertFalse(verify(proof, case, source_sha="c"*40)[
                    "signature_and_subject_verified"])

    def test_wrong_workflow_identity_and_wrong_run_identity_rejected(self):
        case = evidence()
        with tempfile.TemporaryDirectory() as directory:
            proof, bundle, seal_raw = make_proof(directory, case[-1])
            for field, value in (
                ("buildSignerURI", "https://github.com/other/repo/.github/workflows/evil.yml@refs/heads/main"),
                ("githubWorkflowRef", "refs/heads/feature"),
                ("sourceRepositoryDigest", "c"*40),
                ("runInvocationURI", "https://github.com/attacker/repo/actions/runs/1/attempts/1"),
                ("runnerEnvironment", "self-hosted"),
            ):
                with self.subTest(field=field):
                    cert = dict(_certificate(SOURCE, WORKFLOW, RUN, ATTEMPT), **{field: value})
                    with mocked_cli(verified_output(bundle, seal_raw, cert=cert)):
                        denied = verify(proof, case)
                    self.assertEqual(denied["reason"], "SIGNER_CERTIFICATE_IDENTITY_MISMATCH")
                    self.assertFalse(denied["signature_and_subject_verified"])

    def test_wrong_subject_digest_and_extra_subject_rejected(self):
        case = evidence()
        with tempfile.TemporaryDirectory() as directory:
            proof, bundle, raw_seal = make_proof(directory, case[-1])
            for subjects in (
                [{"name":"seal.json","digest":{"sha256":"0"*64}}],
                [{"name":"private-odds.json","digest":{"sha256":hashlib.sha256(raw_seal).hexdigest()}}],
                [{"name":"seal.json","digest":{"sha256":hashlib.sha256(raw_seal).hexdigest()}},
                 {"name":"bonus.json","digest":{"sha256":"0"*64}}],
            ):
                with self.subTest(subject=subjects):
                    with mocked_cli(verified_output(bundle, raw_seal, subject=subjects)):
                        result=verify(proof, case)
                    self.assertEqual(result["reason"], "VERIFIED_SUBJECT_BYTES_MISMATCH")

    def test_rekor_timestamp_late_future_backdated_or_non_utc_cannot_pass(self):
        case = evidence()
        with tempfile.TemporaryDirectory() as directory:
            proof, bundle, raw_seal = make_proof(directory, case[-1])
            for stamp, reason in (
                ("2026-11-02T05:00:59Z", "CLAIMED_PREDICTION_AFTER_WITNESS"),
                ("2026-11-02T07:50:01Z", "WITNESS_AFTER_RECORDED_PREMATCH_CUTOFF"),
                ("2026-11-02T07:10:00Z", "FUTURE_WITNESS_TIMESTAMP"),
                ("2026-11-02T13:02:00+08:00", "NON_UTC_WITNESS_TIME"),
                ("2026-11-02T05:02:00", "NON_UTC_WITNESS_TIME"),
                ("not-a-timestamp", "INVALID_WITNESS_TIME"),
            ):
                with self.subTest(stamp=stamp):
                    with mocked_cli(verified_output(bundle, raw_seal, stamp=stamp)):
                        # Compare a late signed stamp against a later verifier
                        # clock, not one that itself predates that signed stamp.
                        verifier_clock = (datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
                                          if stamp == "2026-11-02T07:50:01Z" else NOW)
                        result = verify(proof, case, now=verifier_clock)
                    self.assertEqual(result["reason"], reason)
                    self.assertEqual(result["certified_independent_forward_samples"], 0)

    def test_tampered_seal_rejected_before_gh_even_with_new_local_sha(self):
        case = evidence()
        with tempfile.TemporaryDirectory() as directory:
            proof, bundle, raw_seal = make_proof(directory, case[-1])
            tampered = deepcopy(case[-1])
            tampered["can_publish_pick"] = True
            (proof / "seal.json").write_text(json.dumps(tampered))
            with patch("private_quote_seal_attestation.subprocess.run") as gh:
                result = verify(proof, case)
            self.assertEqual(result["reason"], "LOCAL_SEAL_REPLAY_REJECTED")
            gh.assert_not_called()

    def test_gh_failure_bogus_saved_output_nonfinite_or_duplicate_keys_cannot_pass(self):
        case = evidence()
        with tempfile.TemporaryDirectory() as directory:
            proof, bundle, raw_seal = make_proof(directory, case[-1])
            payload = verified_output(bundle, raw_seal)
            with mocked_cli(payload, code=1):
                self.assertEqual(verify(proof, case)["reason"], "CRYPTO_VERIFICATION_REJECTED")
            for stdout in (b"[]", b"{}", b'{"one":1,"one":2}',
                           b'[{"verificationResult":NaN}]', b"not-json"):
                with self.subTest(data=stdout):
                    with patch("private_quote_seal_attestation.subprocess.run",
                               return_value=SimpleNamespace(
                                   returncode=0, stdout=stdout, stderr=b"")):
                        denied=verify(proof, case)
                    self.assertFalse(denied["signature_and_subject_verified"])
            with patch("private_quote_seal_attestation.subprocess.run",
                       side_effect=OSError("sensitive unsafe error")):
                denied=verify(proof, case)
            self.assertEqual(denied["reason"], "ATTESTATION_TOOL_UNAVAILABLE_OR_TIMEOUT")

    def test_modified_bundle_output_cannot_masquerade_as_verified_bundle(self):
        case = evidence()
        with tempfile.TemporaryDirectory() as directory:
            proof, bundle, raw_seal = make_proof(directory, case[-1])
            other=dict(bundle, invented="extra")
            with mocked_cli(verified_output(other, raw_seal)):
                denied=verify(proof, case)
            self.assertEqual(denied["reason"], "VERIFIED_BUNDLE_MISMATCH")

    def test_symlink_proof_and_hardlinked_subject_rejected(self):
        case=evidence()
        with tempfile.TemporaryDirectory() as directory:
            proof, _, _ = make_proof(directory, case[-1])
            linked=Path(directory)/"alias"
            linked.symlink_to(proof, target_is_directory=True)
            with patch("private_quote_seal_attestation.subprocess.run") as gh:
                denied=verify(linked, case)
                self.assertEqual(denied["reason"], "UNSAFE_PROOF_PATH")
                duplicate=Path(directory)/"duplicate-seal"
                os.link(proof/"seal.json", duplicate)
                denied=verify(proof, case)
                self.assertEqual(denied["reason"], "UNSAFE_PROOF_FILE")
                gh.assert_not_called()

    def test_cli_private_result_owner_only_without_external_attestation(self):
        case=evidence()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            proof, bundle, seal_raw=make_proof(directory, case[-1])
            raw, receipt, fixture, market, model, _ = case
            private={"raw.json":raw,"receipt.json":json.dumps(receipt).encode(),
                     "fixture.json":json.dumps(fixture).encode(),
                     "market.json":json.dumps(market).encode(),"forecast.json":model}
            for name, value in private.items():
                (root/name).write_bytes(value)
            args=["--proof",str(proof),"--raw-odds",str(root/"raw.json"),
                  "--receipt",str(root/"receipt.json"),"--fixture",str(root/"fixture.json"),
                  "--market",str(root/"market.json"),"--forecast",str(root/"forecast.json"),
                  "--source-sha",SOURCE,"--workflow-sha",WORKFLOW,
                  "--run-id",RUN,"--attempt",ATTEMPT,"--output",str(root/"out.json")]
            with mocked_cli(verified_output(bundle, seal_raw)):
                with redirect_stdout(io.StringIO()) as out:
                    rc=main(args)
            # Real-time CLI invokes current 2026/11/02 or later; the past
            # synthetic Rekor event is not in the future, so this can replay.
            self.assertEqual(rc, 0, out.getvalue())
            data=json.loads((root/"out.json").read_text())
            self.assertTrue(data["signature_and_subject_verified"])
            self.assertEqual(stat.S_IMODE((root/"out.json").stat().st_mode), 0o600)
            with mocked_cli(verified_output(bundle, seal_raw)):
                with redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(main(args), 1)
            self.assertFalse(data["eligible_for_betting_promotion"])


if __name__=="__main__":
    unittest.main()
