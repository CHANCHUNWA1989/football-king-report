"""Synthetic mock-gh contract checks; NOT an actual Sigstore verification."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import live_fixture_attestation_audit as gate


class FixtureWitnessAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.proof = Path(self.temp.name)
        self.kickoff = datetime(2026, 11, 4, 18, 0, tzinfo=timezone.utc)
        self.now = self.kickoff - timedelta(minutes=20)
        self.witness = self.kickoff - timedelta(minutes=30)
        self.source_sha = "1" * 40
        self.workflow_sha = "2" * 40
        self.run_id = "123456789"
        self.attempt = "1"
        self.options = {
            "source_sha": self.source_sha, "workflow_sha": self.workflow_sha,
            "run_id": self.run_id, "attempt": self.attempt, "now": self.now}
        self.manifest = {
            "event_id": "synthetic-fixture-123",
            "kickoff_utc": self.kickoff.isoformat(),
            "registered_at_utc": (self.kickoff - timedelta(minutes=40)).isoformat(),
            "source_events": {
                "score": {"source": "sample-official", "source_event_id": "score-123",
                          "source_url": "https://score.example.org/matches/123"},
                "stats": {"source": "sample-stats", "source_event_id": "stats-123",
                          "source_url": "https://stats.example.org/matches/123"},
                "quote": {"source": "sample-licensed-odds", "source_event_id": "quote-123",
                          "source_url": "https://odds.example.org/matches/123",
                          "provider_market_id": "corners-total-fulltime-123",
                          "market_period": "REGULATION_FULL_TIME",
                          "market_line": 8.5,
                          "selection_ids": {
                              "over": "corners-fulltime-over-8p5-123",
                              "under": "corners-fulltime-under-8p5-123",
                          }},
            },
        }
        self.bundle = {"mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
                       "dsseEnvelope": {"payload": "SYNTHETIC_NOT_A_SIGNATURE"}}
        self.write_proof()
        self.original_sha = hashlib.sha256((self.proof / gate.MANIFEST_NAME).read_bytes()).hexdigest()

    def write_proof(self):
        (self.proof / gate.MANIFEST_NAME).write_text(
            json.dumps(self.manifest, sort_keys=True) + "\n", encoding="utf-8")
        (self.proof / gate.BUNDLE_NAME).write_text(
            json.dumps(self.bundle) + "\n", encoding="utf-8")

    def stdout(self):
        return [{"attestation": {"bundle": copy.deepcopy(self.bundle)},
                 "verificationResult": {
                     "mediaType": "application/vnd.dev.sigstore.verificationresult+json;version=0.1",
                     "signature": {"certificate": gate._certificate(
                         self.source_sha, self.workflow_sha, self.run_id, self.attempt)},
                     "verifiedTimestamps": [{
                         "type": "Tlog", "uri": "https://rekor.sigstore.dev",
                         "timestamp": self.witness.isoformat()}],
                     "statement": {
                         "_type": "https://in-toto.io/Statement/v1",
                         "predicateType": "https://slsa.dev/provenance/v1",
                         "subject": [{
                             "name": gate.MANIFEST_NAME,
                             "digest": {"sha256": self.original_sha}}]}}}]

    def run_audit(self, mock_output=None, **kwargs):
        payload = json.dumps(self.stdout() if mock_output is None else mock_output).encode()
        with patch.object(gate.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, payload, b"")) as run:
            result = gate.audit(self.proof, **dict(self.options, **kwargs))
        return result, run

    def assert_hold(self, result):
        self.assertEqual(result["status"], "HOLD")
        self.assertFalse(result["sigstore_tlog_witness_verified"])
        self.assertFalse(result["manifest_bytes_identity_bound"])
        self.assertFalse(result["eligible_for_betting_promotion"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_mocked_success_only_verifies_witness_not_sources_or_kickoff(self):
        result, call = self.run_audit()
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertTrue(result["sigstore_tlog_witness_verified"])
        self.assertTrue(result["witness_before_recorded_kickoff"])
        for key in ("provider_events_independently_authenticated",
                    "recorded_kickoff_independently_authenticated",
                    "upstream_quote_executable_verified", "certified_positive_ev"):
            self.assertFalse(result[key])
        self.assertEqual(call.call_count, 1)
        argv = call.call_args.args[0]
        self.assertEqual(argv[:3], ["gh", "attestation", "verify"])
        for flag, value in (("--repo", gate.REPOSITORY),
                            ("--signer-workflow", gate.REPOSITORY + "/" + gate.WORKFLOW_PATH),
                            ("--source-ref", "refs/heads/main"),
                            ("--source-digest", self.source_sha),
                            ("--signer-digest", self.workflow_sha)):
            self.assertEqual(argv[argv.index(flag) + 1], value)
        self.assertIn("--deny-self-hosted-runners", argv)
        self.assertFalse(call.call_args.kwargs["shell"])
        self.assertEqual(call.call_args.kwargs["timeout"], 30)

    def test_modified_manifest_bytes_rejected_even_when_shape_still_valid(self):
        self.manifest["source_events"]["quote"]["source_event_id"] = "quote-OTHER"
        self.write_proof()
        result, _ = self.run_audit()
        self.assert_hold(result)
        self.assertEqual(result["reason"], "VERIFIED_SUBJECT_BYTES_MISMATCH")

    def test_self_declared_early_registration_cannot_override_late_tlog(self):
        self.witness = self.kickoff - timedelta(minutes=3)
        result, _ = self.run_audit(now=self.kickoff + timedelta(minutes=1))
        self.assert_hold(result)
        self.assertEqual(result["reason"], "TRUSTED_WITNESS_NOT_PRE_KICKOFF")

    def test_submitted_registration_after_tlog_rejected(self):
        self.manifest["registered_at_utc"] = (self.kickoff - timedelta(minutes=15)).isoformat()
        self.write_proof()
        self.original_sha = hashlib.sha256((self.proof / gate.MANIFEST_NAME).read_bytes()).hexdigest()
        result, _ = self.run_audit()
        self.assert_hold(result)
        self.assertEqual(result["reason"], "REGISTERED_AFTER_TRUSTED_WITNESS")

    def test_forged_certificate_fields_cannot_pass(self):
        for key in gate._certificate(self.source_sha, self.workflow_sha,
                                      self.run_id, self.attempt):
            with self.subTest(field=key):
                payload = self.stdout()
                payload[0]["verificationResult"]["signature"]["certificate"][key] = "forged"
                result, _ = self.run_audit(mock_output=payload)
                self.assert_hold(result)
                self.assertEqual(result["reason"], "CERTIFICATE_IDENTITY_MISMATCH")

    def test_wrong_digest_subject_or_bundle_rejected(self):
        for kind in ("wrong_digest", "wrong_filename", "two_subjects",
                     "wrong_bundle", "two_verifications", "no_tlog",
                     "two_tlogs", "wrong_tlog_uri", "wrong_predicate",
                     "verified_time_in_future"):
            with self.subTest(kind=kind):
                payload = self.stdout()
                item = payload[0]
                v = item["verificationResult"]
                if kind == "wrong_digest":
                    v["statement"]["subject"][0]["digest"]["sha256"] = "0" * 64
                elif kind == "wrong_filename":
                    v["statement"]["subject"][0]["name"] = "../fixture-manifest.json"
                elif kind == "two_subjects":
                    v["statement"]["subject"].append(copy.deepcopy(v["statement"]["subject"][0]))
                elif kind == "wrong_bundle":
                    item["attestation"]["bundle"] = {"fake": True}
                elif kind == "two_verifications":
                    payload.append(copy.deepcopy(item))
                elif kind == "no_tlog":
                    v["verifiedTimestamps"] = []
                elif kind == "two_tlogs":
                    v["verifiedTimestamps"].append(copy.deepcopy(v["verifiedTimestamps"][0]))
                elif kind == "wrong_tlog_uri":
                    v["verifiedTimestamps"][0]["uri"] = "https://other.invalid"
                elif kind == "wrong_predicate":
                    v["statement"]["predicateType"] = "untrusted"
                elif kind == "verified_time_in_future":
                    v["verifiedTimestamps"][0]["timestamp"] = (
                        self.now + timedelta(days=1)).isoformat()
                result, _ = self.run_audit(mock_output=payload)
                self.assert_hold(result)

    def test_failed_or_missing_gh_verification_stays_hold(self):
        cases = (FileNotFoundError(), subprocess.TimeoutExpired("gh", 30),
                 subprocess.CompletedProcess([], 1, b"", b"secret-error"),
                 subprocess.CompletedProcess([], 0, b"not-json", b""))
        for item in cases:
            with self.subTest(item=type(item).__name__):
                kw = {"side_effect": item} if isinstance(item, Exception) else {"return_value": item}
                with patch.object(gate.subprocess, "run", **kw):
                    result = gate.audit(self.proof, **self.options)
                self.assert_hold(result)
                self.assertNotIn("secret-error", json.dumps(result))

    def test_rejects_invalid_manifest_schema_and_source(self):
        for change in ("no_channel", "http_url", "late_registered",
                       "extra_field", "bad_native_id"):
            with self.subTest(change=change):
                m = copy.deepcopy(self.manifest)
                if change == "no_channel":
                    del m["source_events"]["quote"]
                elif change == "http_url":
                    m["source_events"]["stats"]["source_url"] = "http://stats.example.org/foo"
                elif change == "late_registered":
                    m["registered_at_utc"] = (self.kickoff - timedelta(minutes=1)).isoformat()
                elif change == "extra_field":
                    m["certified_positive_ev"] = True
                else:
                    m["source_events"]["quote"]["source_event_id"] = True
                with self.assertRaises(gate.WitnessError):
                    gate.validate_manifest(m)

    def test_public_manifest_rejects_query_parameters(self):
        # A public Sigstore fixture manifest must never contain URL queries,
        # including possible token/API-key credentials.
        for query in ("?api_key=sample-do-not-use", "?token=dummy", "?fixture=123"):
            with self.subTest(query=query):
                document = copy.deepcopy(self.manifest)
                document["source_events"]["quote"]["source_url"] += query
                with self.assertRaisesRegex(
                        gate.WitnessError, "INVALID_FIXTURE_SOURCE_URL"):
                    gate.validate_manifest(document)

    def test_public_manifest_requires_market_id_and_fulltime_period(self):
        for value in (None, True, "", "FIRST_HALF", "REGULATION_EXTRA_TIME"):
            with self.subTest(value=value):
                doc = copy.deepcopy(self.manifest)
                doc["source_events"]["quote"]["market_period"] = value
                with self.assertRaises(gate.WitnessError):
                    gate.validate_manifest(doc)
        for value in (None, True, "", "bad/id"):
            with self.subTest(market_id=value):
                doc = copy.deepcopy(self.manifest)
                doc["source_events"]["quote"]["provider_market_id"] = value
                with self.assertRaises(gate.WitnessError):
                    gate.validate_manifest(doc)

    def test_public_manifest_missing_market_binding_rejected(self):
        for field in ("provider_market_id", "market_period"):
            with self.subTest(field=field):
                doc = copy.deepcopy(self.manifest)
                del doc["source_events"]["quote"][field]
                with self.assertRaises(gate.WitnessError):
                    gate.validate_manifest(doc)

    def test_signed_corner_line_invalid_is_hold(self):
        for value in (-1, True, None, 8.3, float("inf"), 10000):
            with self.subTest(line=value):
                document = copy.deepcopy(self.manifest)
                document["source_events"]["quote"]["market_line"] = value
                with self.assertRaises(gate.WitnessError):
                    gate.validate_manifest(document)

    def test_signed_corner_selection_ids_missing_or_malformed_hold(self):
        for value in (None, [], {}, {"over": "over-only"}, {
            "over": "duplicate", "under": "duplicate"
        }, {"over": "over-valid", "under": True}):
            with self.subTest(value=value):
                document = copy.deepcopy(self.manifest)
                document["source_events"]["quote"]["selection_ids"] = value
                with self.assertRaises(gate.WitnessError):
                    gate.validate_manifest(document)

    def test_signed_corner_line_and_selection_keys_required(self):
        for key in ("market_line", "selection_ids"):
            with self.subTest(key=key):
                document = copy.deepcopy(self.manifest)
                del document["source_events"]["quote"][key]
                with self.assertRaises(gate.WitnessError):
                    gate.validate_manifest(document)

    def test_duplicated_json_keys_rejected(self):
        (self.proof / gate.MANIFEST_NAME).write_text(
            '{"event_id":"one","event_id":"two"}', encoding="utf-8")
        result, _ = self.run_audit()
        self.assert_hold(result)
        self.assertEqual(result["reason"], "DUPLICATE_JSON_KEY")

    def test_symlink_and_oversized_inputs_rejected(self):
        manifest_file = self.proof / gate.MANIFEST_NAME
        manifest_file.unlink()
        manifest_file.symlink_to(self.proof / gate.BUNDLE_NAME)
        result, _ = self.run_audit()
        self.assert_hold(result)
        manifest_file.unlink()
        manifest_file.write_bytes(b"x" * (gate.MAX_MANIFEST_BYTES + 1))
        result, _ = self.run_audit()
        self.assert_hold(result)

    def test_bad_context_and_missing_bundle_do_not_call_verifier(self):
        with patch.object(gate.subprocess, "run") as run:
            result = gate.audit(self.proof, **dict(self.options, source_sha="bad"))
        self.assert_hold(result)
        run.assert_not_called()
        (self.proof / gate.BUNDLE_NAME).unlink()
        with patch.object(gate.subprocess, "run") as run:
            result = gate.audit(self.proof, **self.options)
        self.assert_hold(result)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
