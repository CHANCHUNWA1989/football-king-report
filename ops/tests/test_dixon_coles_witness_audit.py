"""Mocked CLI policy tests; these fixtures are not cryptographic evidence."""
import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import forecast_provenance_audit as provenance
import test_forecast_provenance_audit as proof_fixture
from test_dixon_coles_forward_integration import NOW, shadow_document
from model_dixon_coles_forward import TOP_KEY, build
from dixon_coles_witness_audit import audit, main


class DixonColesWitnessTests(unittest.TestCase):
    def setUp(self):
        self.fixture = proof_fixture.ForecastProvenanceAuditTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.proof = self.fixture.proof
        self.fixture.shadow = shadow_document()
        self.fixture.shadow[TOP_KEY] = build(self.fixture.shadow, now=NOW)
        self.fixture.paired = {"status": "HOLD", "matched_count": 0,
                               "comparisons": [], "production_recommendations": "DISABLED"}
        self.fixture.slate.update(verification_rows=0, point_in_time_market_pairs=0, rows=[])
        self.options = {**self.fixture.options, "now": NOW + timedelta(minutes=1)}
        self.witness = NOW + timedelta(seconds=1)
        self.fixture.write_inputs()

    def run_audit(self, *, returncode=0):
        self.fixture.write_inputs()
        stdout = self.fixture.stdout()
        stdout[0]["verificationResult"]["verifiedTimestamps"][0]["timestamp"] = self.witness.isoformat()
        completed = subprocess.CompletedProcess([], returncode, json.dumps(stdout).encode(), b"")
        with patch("forecast_provenance_audit.subprocess.run", return_value=completed) as runner:
            result = audit(self.proof, **self.options)
        return result, runner

    def test_fresh_verification_binds_formula_source_and_recorded_time_only(self):
        before = {p.name: p.read_bytes() for p in self.proof.iterdir()}
        result, runner = self.run_audit()
        self.assertEqual(runner.call_count, 3)
        self.assertTrue(result["audit_completed"])
        self.assertTrue(result["signature_identity_and_subjects_verified"])
        self.assertTrue(result["candidate_bytes_formula_source_binding_verified"])
        self.assertEqual(result["observed_before_recorded_kickoff_count"], 1)
        for field in ("recorded_kickoff_independently_authenticated",
                      "outcomes_independently_authenticated", "eligible_for_betting_promotion",
                      "betting_roi_estimable", "automatic_model_promotion"):
            self.assertIs(result[field], False)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.proof.iterdir()})

    def test_missing_legacy_capture_is_not_reconstructed(self):
        del self.fixture.shadow[TOP_KEY]
        result, runner = self.run_audit()
        self.assertEqual(runner.call_count, 3)
        self.assertTrue(result["audit_completed"])
        self.assertFalse(result["candidate_capture_present"])
        self.assertFalse(result["candidate_bytes_formula_source_binding_verified"])
        self.assertEqual(result["cases"], [])
        self.assertEqual(result["observed_before_recorded_kickoff_count"], 0)

    def test_registered_default_clock_rewind_empty_is_no_formula_evidence(self):
        with patch("model_dixon_coles_forward._clock", side_effect=[NOW, NOW, NOW-timedelta(seconds=1)]):
            empty = build(self.fixture.shadow)
        self.assertEqual(empty["source_problem"], "CAPTURE_CLOCK_REWOUND")
        self.fixture.shadow[TOP_KEY] = empty
        result, _ = self.run_audit()
        self.assertTrue(result["audit_completed"])
        self.assertTrue(result["candidate_capture_present"])
        self.assertFalse(result["candidate_bytes_formula_source_binding_verified"])
        self.assertEqual(result["observed_before_recorded_kickoff_count"], 0)

    def test_nonempty_payload_mutations_and_bool_number_aliases_fail_batch(self):
        original = copy.deepcopy(self.fixture.shadow[TOP_KEY])
        mutations = [
            lambda c: c.update(predictions_count=True),
            lambda c: c.update(automatic_model_promotion=0),
            lambda c: c.update(model_id="other"),
            lambda c: c["predictions"][0]["candidate"].__setitem__(0, .9),
            lambda c: c["predictions"][0].update(source_projection_sha256="0"*64),
            lambda c: c["predictions"][0].update(training_games=50.0),
            lambda c: c["protocol"].update(parameter_refitting_permitted=0),
            lambda c: c["predictions"].append(copy.deepcopy(c["predictions"][0])),
        ]
        for mutate in mutations:
            self.fixture.shadow[TOP_KEY] = copy.deepcopy(original)
            mutate(self.fixture.shadow[TOP_KEY])
            result, _ = self.run_audit()
            self.assertFalse(result["audit_completed"])
            self.assertTrue(result["signature_identity_and_subjects_verified"])
            self.assertEqual(result["cases"], [])
            self.assertEqual(result["observed_before_recorded_kickoff_count"], 0)

    def test_null_capture_and_unsafe_empty_metadata_are_rejected(self):
        self.fixture.shadow[TOP_KEY] = None
        self.assertFalse(self.run_audit()[0]["audit_completed"])
        empty = build({**self.fixture.shadow, "predictions": [],
                       "predictions_count": 0, "status": "HOLD"}, now=NOW)
        for field, value in (("predictions_count", False), ("automatic_model_promotion", 0),
                             ("exclusions", {"BAD": True}), ("protocol_sha256", "0"*64)):
            changed = copy.deepcopy(empty); changed[field] = value
            self.fixture.shadow[TOP_KEY] = changed
            self.assertFalse(self.run_audit()[0]["audit_completed"])

    def test_trusted_witness_cannot_precede_candidate_completion(self):
        self.witness = NOW-timedelta(microseconds=1)
        result, _ = self.run_audit()
        self.assertTrue(result["audit_completed"])
        self.assertTrue(result["candidate_bytes_formula_source_binding_verified"])
        self.assertEqual(result["observed_before_recorded_kickoff_count"], 0)

    def test_witness_lead_is_strict_and_offsets_preserve_the_same_instant(self):
        kickoff = NOW+timedelta(hours=2)
        offset = timezone(timedelta(hours=8))
        source = datetime.fromisoformat(self.fixture.shadow["as_of_utc"]).astimezone(offset).isoformat()
        self.fixture.shadow["as_of_utc"] = source
        self.fixture.shadow["predictions"][0]["prediction_utc"] = source
        for lead, count in ((599, 0), (600, 0), (601, 1)):
            # Verified Rekor timestamps retain the inherited UTC-only rule.
            self.witness = kickoff-timedelta(seconds=lead)
            self.options["now"] = kickoff
            result, _ = self.run_audit()
            self.assertTrue(result["audit_completed"])
            self.assertEqual(result["observed_before_recorded_kickoff_count"], count)

    def test_saved_verified_claims_cannot_replace_failed_fresh_cli(self):
        (self.proof/"shadow.verification.json").write_text('[{"verified":true}]')
        result, _ = self.run_audit(returncode=1)
        self.assertFalse(result["audit_completed"])
        self.assertFalse(result["signature_identity_and_subjects_verified"])
        self.assertEqual(result["observed_before_recorded_kickoff_count"], 0)

    def test_shadow_change_after_verification_is_detected(self):
        original = provenance.audit
        self.fixture.write_inputs()
        stdout = self.fixture.stdout()
        stdout[0]["verificationResult"]["verifiedTimestamps"][0]["timestamp"] = self.witness.isoformat()
        completed = subprocess.CompletedProcess([], 0, json.dumps(stdout).encode(), b"")
        def change_after(*args, **kwargs):
            verified = original(*args, **kwargs)
            path = self.proof/"shadow.json"; path.write_bytes(path.read_bytes()+b"\n")
            return verified
        with patch("forecast_provenance_audit.subprocess.run", return_value=completed), \
             patch("dixon_coles_witness_audit.provenance.audit", side_effect=change_after):
            result = audit(self.proof, **self.options)
        self.assertFalse(result["audit_completed"])
        self.assertFalse(result["signature_identity_and_subjects_verified"])
        self.assertEqual(result["observed_before_recorded_kickoff_count"], 0)

    def test_changed_invalid_row_exclusion_priority_remains_fail_closed(self):
        bad = copy.deepcopy(self.fixture.shadow["predictions"][0])
        bad.update(event_id="other-event", home="Second internal home",
                   kickoff_utc=(NOW+timedelta(seconds=601)).isoformat(), training_games=True)
        self.fixture.shadow["predictions"].append(bad)
        self.fixture.shadow["predictions_count"] = 2
        with patch("model_dixon_coles_forward._clock", side_effect=[NOW, NOW, NOW+timedelta(seconds=2)]):
            captured = build(self.fixture.shadow)
        self.assertEqual(captured["predictions_count"], 1)
        self.assertIn("INVALID_TRAINING_PROVENANCE", captured["exclusions"])
        self.fixture.shadow[TOP_KEY] = captured
        self.witness = NOW+timedelta(seconds=3)
        result, _ = self.run_audit()
        self.assertFalse(result["audit_completed"])
        self.assertEqual(result["reason"], "REGISTERED_CAPTURE_RECONSTRUCTION_MISMATCH")
        self.assertEqual(result["observed_before_recorded_kickoff_count"], 0)

    def test_cli_output_cannot_overwrite_signed_source_or_enter_proof_directory(self):
        source = self.proof/"shadow.json"; before = source.read_bytes()
        with tempfile.TemporaryDirectory() as outside:
            alias = Path(outside)/"alias.json"
            os.link(source, alias)
            for output in (source, self.proof/"new-audit.json", alias):
                argv = ["--proof", str(self.proof), "--source-sha", self.options["source_sha"],
                        "--workflow-sha", self.options["workflow_sha"], "--run-id", self.options["run_id"],
                        "--attempt", "1", "--output", str(output)]
                with patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit):
                    main(argv)
                self.assertEqual(source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
