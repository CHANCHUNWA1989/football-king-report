"""Fresh capture proof and explicit missing result evidence stay distinct.

The only mocked boundary is the existing cryptographic capture audit.  Original
capture bytes still pass the real canonical tar and source-display replayers.
These synthetic fixtures are never evidence of real match results.
"""
import copy
from contextlib import redirect_stderr
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from ops import trusted_result_evidence
from ops.tests import test_ndr_capture_pack as capture_fixture
from ops.tests.test_ndr_completion_observations import detail
from ops.tests.test_ndr_result_observations import row


SOURCE, WORKFLOW_SHA, RUN = "1" * 40, "2" * 40, "39133031901"
NOW = capture_fixture.NOW


class TrustedResultEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.proof = self.root / "proof"
        self.proof.mkdir()
        self.options = dict(source_sha=SOURCE, workflow_sha=WORKFLOW_SHA,
                            run_id=RUN, attempt="1", now=NOW)
        self.make_capture()

    def make_capture(self, **kwargs):
        fixture_root = self.root / ("fixture-" + str(len(list(self.root.glob("fixture-*")))))
        fixture_root.mkdir()
        self.raw, self.summary = capture_fixture.NDRCapturePackTests().capture(fixture_root, **kwargs)
        self.bundle = b'{"synthetic_test_bundle":true}\n'
        (self.proof / "ndr-capture.tar").write_bytes(self.raw)
        (self.proof / "capture.sigstore.json").write_bytes(self.bundle)

    def capture_audit(self):
        return {
            "audit_completed": True,
            "signature_identity_and_subject_verified": True,
            "capture_content_replayed": True,
            "subject_sha256": {"ndr-capture.tar": hashlib.sha256(self.raw).hexdigest()},
            "bundle_sha256": hashlib.sha256(self.bundle).hexdigest(),
            "verified_tlog_utc": NOW.isoformat(),
            "capture_summary": copy.deepcopy(self.summary),
            "source_commit": SOURCE, "workflow_commit": WORKFLOW_SHA,
            "run_id": RUN, "run_attempt": "1",
            "status": "HOLD", "production_recommendations": "DISABLED",
            "independently_verified": False, "eligible_for_model_scoring": False,
        }

    def run_audit(self, capture_report=None, *, side_effect=None):
        kwargs = {"side_effect": side_effect} if side_effect is not None else {
            "return_value": self.capture_audit() if capture_report is None else capture_report}
        with patch("ops.trusted_result_evidence.capture_provenance.audit", **kwargs) as fresh:
            report = trusted_result_evidence.audit(self.proof, **self.options)
        fresh.assert_called_once_with(self.proof, **self.options)
        return report

    def assert_held(self, report, *, completed):
        self.assertIs(report["audit_completed"], completed)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertEqual(report["independently_verified_count"], 0)
        self.assertIs(report["eligible_for_model_scoring"], False)
        if not completed:
            self.assertEqual(report["cases"], [])
            self.assertIsInstance(report["reason"], str)
            self.assertTrue(report["reason"])

    def test_fresh_capture_and_real_replay_yield_only_provider_local_case(self):
        originals = {p.name: p.read_bytes() for p in self.proof.iterdir()}
        report = self.run_audit()
        self.assert_held(report, completed=True)
        self.assertEqual(len(report["cases"]), 1)
        case = report["cases"][0]
        self.assertEqual(case["provider_fixture_id"], "5884")
        self.assertEqual(case["home_provider_team_id"], "264")
        self.assertEqual(case["away_provider_team_id"], "110")
        self.assertEqual(case["display_score"], {"home": 1, "away": 0})
        self.assertEqual(case["provider_local_identity_status"], "PROVIDER_LOCAL_DISPLAY_MATCHED")
        self.assertEqual(case["cross_source_fixture_mapping_status"], "UNKNOWN")
        self.assertEqual(case["upstream_independence_status"], "UNKNOWN")
        self.assertEqual(case["regulation_result_status"], "UNVERIFIED")
        self.assertIs(case["independently_verified"], False)
        self.assertTrue(case["blockers"])
        self.assertEqual(originals, {p.name: p.read_bytes() for p in self.proof.iterdir()})

    def test_provider_local_display_and_log_witness_do_not_invent_actual_kickoff(self):
        report = self.run_audit()
        self.assert_held(report, completed=True)
        case = report["cases"][0]
        self.assertIsNone(case["actual_kickoff_utc"])
        self.assertEqual(case["actual_kickoff_status"], "UNKNOWN")
        self.assertNotIn("kickoff_utc", case)
        self.assertNotIn("score_ft", case)
        self.assertNotIn("ft", case)
        self.assertNotIn("y", case)

    def test_missing_chain_facts_have_explicit_actionable_blockers(self):
        report = self.run_audit()
        self.assert_held(report, completed=True)
        blockers = json.dumps(report["cases"][0]["blockers"]).upper()
        self.assertIn("KICKOFF", blockers)
        self.assertIn("INDEPEND", blockers)
        self.assertTrue("REGULATION" in blockers or "PERIOD" in blockers or "90" in blockers)
        self.assertTrue("MAPPING" in blockers or "IDENTITY" in blockers)

    def test_coverage_distinguishes_accepted_attempted_observed_and_uncovered(self):
        rows = "".join(row(fixture=str(5884 + i), home=str(264 + i)) for i in range(5))
        self.make_capture(rows=rows)
        report = self.run_audit()
        self.assert_held(report, completed=True)
        self.assertEqual(report["coverage"], {
            "accepted_index_fixture_ids": ["5884", "5885", "5886", "5887", "5888"],
            "attempted_detail_fixture_ids": ["5888", "5884", "5885"],
            "observed_fixture_ids": ["5884"],
            "uncovered_fixture_ids": ["5885", "5886", "5887", "5888"],
        })
        self.assertEqual(report['selection_policy'], 'UTC_DAY_CYCLIC_NUMERIC_FIXTURE_IDS_V1')
        self.assertEqual(report['selection']['selected_fixture_ids'], ['5888', '5884', '5885'])
        self.assertEqual([case["provider_fixture_id"] for case in report["cases"]], ["5884"])

    def test_fetch_failure_is_attempted_but_not_observed_or_certified(self):
        self.make_capture(bodies={"5884": URLError("PRIVATE_UPSTREAM_ERROR")})
        report = self.run_audit()
        self.assert_held(report, completed=True)
        self.assertEqual(report["cases"], [])
        self.assertEqual(report["coverage"]["accepted_index_fixture_ids"], ["5884"])
        self.assertEqual(report["coverage"]["attempted_detail_fixture_ids"], ["5884"])
        self.assertEqual(report["coverage"]["observed_fixture_ids"], [])
        self.assertEqual(report["coverage"]["uncovered_fixture_ids"], ["5884"])
        self.assertNotIn("PRIVATE_UPSTREAM_ERROR", json.dumps(report))

    def test_coherent_source_unavailable_has_empty_coverage_not_old_cases(self):
        self.make_capture(missing=True)
        report = self.run_audit()
        self.assert_held(report, completed=True)
        self.assertEqual(report["cases"], [])
        self.assertEqual(report["coverage"], {
            "accepted_index_fixture_ids": [], "attempted_detail_fixture_ids": [],
            "observed_fixture_ids": [], "uncovered_fixture_ids": [],
        })

    def test_detail_without_explicit_end_is_uncovered_despite_numeric_score(self):
        self.make_capture(bodies={"5884": detail().replace(b">Ende<", b">Live<")})
        report = self.run_audit()
        self.assert_held(report, completed=True)
        self.assertEqual(report["cases"], [])
        self.assertEqual(report["coverage"]["observed_fixture_ids"], [])
        self.assertEqual(report["coverage"]["uncovered_fixture_ids"], ["5884"])

    def test_saved_verification_json_never_overrides_fresh_capture_failure(self):
        saved = {"audit_completed": True, "independently_verified": True,
                 "independently_verified_count": 300, "eligible_for_model_scoring": True,
                 "production_recommendations": "ENABLED", "cases": [{"score_ft": "1:0"}]}
        for name in ("verification.json", "capture.verification.json", "ndr-capture-audit.json",
                     "trusted-result-evidence.json"):
            (self.proof / name).write_text(json.dumps(saved))
        failed = dict(self.capture_audit(), audit_completed=False,
                      signature_identity_and_subject_verified=False,
                      reason="ATTESTATION_CLI_REJECTED")
        report = self.run_audit(failed)
        self.assert_held(report, completed=False)
        self.assertIn("CAPTURE", report["reason"])

    def test_saved_true_flags_and_caller_groups_never_upgrade_successful_observation(self):
        (self.proof / "verification.json").write_text(json.dumps({
            "independently_verified": True, "source_groups": {"NDR": "A", "DFB": "B"},
            "result_period": "REGULATION", "actual_kickoff_utc": "2026-10-16T18:30:00Z"}))
        report = self.run_audit()
        self.assert_held(report, completed=True)
        self.assertIs(report["cases"][0]["independently_verified"], False)
        self.assertEqual(report["cases"][0]["upstream_independence_status"], "UNKNOWN")
        self.assertIsNone(report["cases"][0]["actual_kickoff_utc"])

    def test_every_capture_authentication_stage_must_be_explicit_true(self):
        for key in ("audit_completed", "signature_identity_and_subject_verified", "capture_content_replayed"):
            for invalid in (False, None, 1, "true"):
                with self.subTest(key=key, invalid=invalid):
                    capture = self.capture_audit()
                    capture[key] = invalid
                    self.assert_held(self.run_audit(capture), completed=False)

    def test_tar_or_bundle_changed_after_fresh_capture_verification_is_rejected(self):
        for name, expected in (("ndr-capture.tar", "CAPTURE_BYTES_CHANGED_AFTER_VERIFICATION"),
                               ("capture.sigstore.json", "BUNDLE_BYTES_CHANGED_AFTER_VERIFICATION")):
            with self.subTest(name=name):
                original = (self.proof / name).read_bytes()
                capture = self.capture_audit()
                def changed(*args, **kwargs):
                    (self.proof / name).write_bytes(original + b" ")
                    return capture
                report = self.run_audit(side_effect=changed)
                self.assert_held(report, completed=False)
                self.assertEqual(report["reason"], expected)
                (self.proof / name).write_bytes(original)

    def test_invalid_capture_raw_is_replayed_even_if_fresh_boundary_is_forged(self):
        self.raw = b"not a canonical tar even with matching claimed digest"
        (self.proof / "ndr-capture.tar").write_bytes(self.raw)
        report = self.run_audit()
        self.assert_held(report, completed=False)
        self.assertTrue("CAPTURE" in report["reason"] or "REPLAY" in report["reason"])

    def test_replayed_content_rejects_false_observation_in_signed_looking_capture(self):
        files = capture_fixture.unpack(self.raw)
        stored = json.loads(files["report.json"])
        stored["observations"][0]["display_score"]["home"] = 2
        files["report.json"] = capture_fixture.encode(stored)
        self.raw = capture_fixture.repack(files)
        (self.proof / "ndr-capture.tar").write_bytes(self.raw)
        report = self.run_audit()
        self.assert_held(report, completed=False)

    def test_pinned_source_policy_digest_rejects_relabelled_upstream_groups(self):
        forged = self.root / "forged-policy.json"
        policy = json.loads(trusted_result_evidence.POLICY_FILE.read_bytes())
        policy["providers"]["NDR"]["upstream_relationship"] = "INDEPENDENT"
        policy["providers"]["NDR"]["independent_result_collection_evidence"] = ["https://www.ndr.de/"]
        forged.write_text(json.dumps(policy))
        with patch("ops.trusted_result_evidence.POLICY_FILE", forged):
            report = self.run_audit()
        self.assert_held(report, completed=False)
        self.assertEqual(report["reason"], "SOURCE_POLICY_DIGEST_MISMATCH")

    def test_policy_general_publisher_clues_do_not_authenticate_result_feed(self):
        policy = json.loads(trusted_result_evidence.POLICY_FILE.read_bytes())
        self.assertEqual(policy["providers"]["NDR"]["upstream_relationship"], "UNKNOWN")
        self.assertEqual(policy["providers"]["DFB"]["upstream_relationship"], "UNKNOWN")
        report = self.run_audit()
        self.assert_held(report, completed=True)
        self.assertEqual(report["cases"][0]["upstream_independence_status"], "UNKNOWN")

    def cli_args(self, output, capture_output=None):
        args = ["--proof", str(self.proof), "--source-sha", SOURCE,
                "--workflow-sha", WORKFLOW_SHA, "--run-id", RUN, "--attempt", "1",
                "--output", str(output)]
        if capture_output is not None:
            args += ["--capture-audit-output", str(capture_output)]
        return args

    def assert_cli_preflight_rejected(self, output, capture_output=None):
        originals = {p.name: p.read_bytes() for p in self.proof.iterdir() if p.is_file()}
        with patch("ops.trusted_result_evidence.capture_provenance.audit") as fresh, \
             redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as rejected:
                trusted_result_evidence.main(self.cli_args(output, capture_output))
        self.assertEqual(rejected.exception.code, 2)
        fresh.assert_not_called()
        self.assertEqual(originals, {
            p.name: p.read_bytes() for p in self.proof.iterdir() if p.is_file()})

    def test_cli_fresh_synthetic_boundary_writes_separate_new_hold_reports(self):
        originals = {p.name: p.read_bytes() for p in self.proof.iterdir()}
        output, capture_output = self.root / "result-evidence.json", self.root / "capture-audit.json"
        with patch("ops.trusted_result_evidence.capture_provenance.audit",
                   return_value=self.capture_audit()) as fresh, \
             patch("ops.trusted_result_evidence.datetime", wraps=datetime) as clock:
            clock.now.return_value = NOW
            code = trusted_result_evidence.main(self.cli_args(output, capture_output))
        self.assertEqual(code, 0)
        fresh.assert_called_once_with(self.proof, source_sha=SOURCE, workflow_sha=WORKFLOW_SHA,
                                      run_id=RUN, attempt="1", now=None)
        result = json.loads(output.read_bytes())
        self.assert_held(result, completed=True)
        self.assertEqual(json.loads(capture_output.read_bytes()), result["capture_audit"])
        for path in (output, capture_output):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.stat().st_nlink, 1)
        self.assertEqual(originals, {p.name: p.read_bytes() for p in self.proof.iterdir()})

    def test_cli_capture_failure_returns_failure_and_writes_safe_derived_report(self):
        output = self.root / "failed-result-evidence.json"
        failed = dict(self.capture_audit(), audit_completed=False, reason="ATTESTATION_CLI_REJECTED")
        with patch("ops.trusted_result_evidence.capture_provenance.audit", return_value=failed) as fresh:
            code = trusted_result_evidence.main(self.cli_args(output))
        self.assertEqual(code, 1)
        self.assertEqual(fresh.call_count, 1)
        self.assert_held(json.loads(output.read_bytes()), completed=False)
        self.assertEqual((self.proof / "ndr-capture.tar").read_bytes(), self.raw)
        self.assertEqual((self.proof / "capture.sigstore.json").read_bytes(), self.bundle)

    def test_cli_cannot_write_reports_inside_proof_or_overwrite_existing_output(self):
        self.assert_cli_preflight_rejected(self.proof / "new-report.json")
        output = self.root / "already-present.json"
        output.write_bytes(b"PRIVATE_EXISTING_REPORT")
        self.assert_cli_preflight_rejected(output)
        self.assertEqual(output.read_bytes(), b"PRIVATE_EXISTING_REPORT")
        self.assert_cli_preflight_rejected(self.root / "new-result.json", output)
        self.assertFalse((self.root / "new-result.json").exists())

    def test_cli_distinct_outputs_cannot_alias_one_another(self):
        output = self.root / "same-output.json"
        self.assert_cli_preflight_rejected(output, output)
        self.assertFalse(output.exists())

    def test_cli_missing_parent_is_rejected_before_any_fresh_verification(self):
        missing = self.root / "nonexistent-parent" / "report.json"
        self.assert_cli_preflight_rejected(missing)
        self.assertFalse(missing.parent.exists())

    def test_cli_rejects_output_symlink_and_symlink_ancestor(self):
        target = self.root / "existing-target.json"
        target.write_bytes(b"TARGET_MUST_SURVIVE")
        link = self.root / "output-link.json"
        link.symlink_to(target)
        self.assert_cli_preflight_rejected(link)
        alias_parent = self.root / "aliased-parent"
        alias_parent.symlink_to(self.root, target_is_directory=True)
        self.assert_cli_preflight_rejected(alias_parent / "new-output.json")
        self.assertEqual(target.read_bytes(), b"TARGET_MUST_SURVIVE")

    def test_cli_output_hardlinks_cannot_modify_either_original(self):
        for original_name in ("ndr-capture.tar", "capture.sigstore.json"):
            with self.subTest(original_name=original_name):
                output = self.root / (original_name + ".derived")
                os.link(self.proof / original_name, output)
                self.assert_cli_preflight_rejected(output)
                self.assertEqual(output.read_bytes(), (self.proof / original_name).read_bytes())
                output.unlink()

    def test_cli_exclusive_output_creation_rejects_file_appearing_during_audit(self):
        output = self.root / "raced-output.json"
        def raced(*args, **kwargs):
            output.write_bytes(b"CONCURRENT_FILE_MUST_SURVIVE")
            return self.capture_audit()
        with patch("ops.trusted_result_evidence.capture_provenance.audit", side_effect=raced) as fresh, \
             patch("ops.trusted_result_evidence.datetime", wraps=datetime) as clock:
            clock.now.return_value = NOW
            code = trusted_result_evidence.main(self.cli_args(output))
        self.assertEqual(code, 1)
        self.assertEqual(fresh.call_count, 1)
        self.assertEqual(output.read_bytes(), b"CONCURRENT_FILE_MUST_SURVIVE")

    def test_audit_rejects_unsafe_original_symlink_even_after_claimed_verification(self):
        original = self.proof / "ndr-capture.tar"
        safe_target = self.root / "original-tar-bytes"
        original.rename(safe_target)
        original.symlink_to(safe_target)
        report = self.run_audit()
        self.assert_held(report, completed=False)
        self.assertEqual(safe_target.read_bytes(), self.raw)

    def test_audit_rejects_original_hardlink_even_after_claimed_verification(self):
        alias = self.root / "bundle-alias.json"
        os.link(self.proof / "capture.sigstore.json", alias)
        report = self.run_audit()
        self.assert_held(report, completed=False)
        self.assertEqual(alias.read_bytes(), self.bundle)


if __name__ == "__main__":
    unittest.main()
