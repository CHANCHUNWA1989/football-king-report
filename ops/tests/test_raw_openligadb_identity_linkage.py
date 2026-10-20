"""Raw fixed-ID policy tests; mocked gh stdout is not cryptographic proof."""
import copy
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_forecast_provenance_audit as provenance_tests


class RawOpenLigaDBIdentityLinkageTests(unittest.TestCase):
    def setUp(self):
        self.fixture = provenance_tests.ForecastProvenanceAuditTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.proof
        self.proof = self.root / "proof"
        self.proof.mkdir()
        self.fixture.proof = self.proof
        self.raw_dir = self.root / "raw"
        self.raw_dir.mkdir()
        self.fixture.forecast["event_id"] = "openligadb:83212"
        self.fixture.pair.update(
            forecast_event_id="openligadb:83212",
            source_fixture_identity={"provider": "OpenLigaDB", "match_id": "83212"},
            source_fixture_identity_status="UNAUTHENTICATED",
            independently_verified=False, eligible_for_model_scoring=False)
        self.fixture.write_inputs()
        self.raw = [{"matchID": 83212,
                     "matchDateTimeUTC": self.fixture.pair["kickoff_utc"],
                     "matchIsFinished": False,
                     "team1": {"teamId": 40, "teamName": "Bayern"},
                     "team2": {"teamId": 7, "teamName": "Dortmund"},
                     "matchResults": []}]
        self.manifest = {
            "schema": "football-king-raw-ft-source-candidates-v1",
            "status": "HOLD", "production_recommendations": "DISABLED",
            "independently_verified": False, "season_start": 2026,
            "captured_utc": "2026-10-18T14:00:00Z", "sources": [{
                "provider": "OpenLigaDB", "status": "FETCHED_UNVERIFIED",
                "source_url": "https://api.openligadb.de/getmatchdata/bl1/2026",
                "raw_file": "openligadb.json"}]}
        self.write_raw()

    def module(self):
        self.assertIsNotNone(importlib.util.find_spec("raw_openligadb_identity_linkage"),
                             "No replayable raw matchID/teamId linkage boundary exists")
        return importlib.import_module("raw_openligadb_identity_linkage")

    def write_raw(self):
        body = json.dumps(self.raw).encode()
        (self.raw_dir / "openligadb.json").write_bytes(body)
        self.manifest["sources"][0].update(
            raw_sha256=hashlib.sha256(body).hexdigest(), bytes=len(body))
        self.write_manifest()

    def write_manifest(self):
        (self.raw_dir / "manifest.json").write_text(json.dumps(self.manifest))

    def run_linkage(self):
        module = self.module()
        stdout = json.dumps(self.fixture.stdout()).encode()
        with patch("forecast_provenance_audit.subprocess.run", return_value=
                   subprocess.CompletedProcess([], 0, stdout, b"")) as run:
            report = module.audit_linkage(self.raw_dir, self.proof, **self.fixture.options)
        return report, run

    def assert_held(self, report):
        for item in [report] + report["cases"] + report["sealed_exclusions"]:
            self.assertEqual(item["status"], "HOLD")
            self.assertEqual(item["production_recommendations"], "DISABLED")
            for field in ("independently_verified", "eligible_for_model_scoring",
                          "eligible_for_betting_promotion", "raw_source_authenticated",
                          "raw_capture_time_authenticated", "original_endpoint_verified",
                          "source_freshness_verified", "forecast_team_ids_verified",
                          "actual_kickoff_independently_authenticated",
                          "regulation_90_minute_ft_authenticated",
                          "outcomes_independently_authenticated"):
                self.assertIs(item[field], False, field)

    def finished(self):
        self.raw[0].update(matchIsFinished=True, matchResults=[{
            "resultTypeID": 2, "pointsTeam1": 2, "pointsTeam2": 1}])
        self.manifest["captured_utc"] = "2026-10-18T18:00:00Z"
        self.fixture.options["now"] = datetime(2026, 10, 18, 18, 30, tzinfo=timezone.utc)
        self.write_raw()

    def cli(self, output):
        return self.module().main([
            "--raw-dir", str(self.raw_dir), "--proof", str(self.proof),
            "--source-sha", self.fixture.options["source_sha"],
            "--workflow-sha", self.fixture.options["workflow_sha"],
            "--run-id", self.fixture.options["run_id"], "--attempt", "1",
            "--output", str(output)])

    def test_exact_future_scheduled_fixed_id_links_without_ft(self):
        report, run = self.run_linkage()
        self.assertTrue(report["audit_completed"])
        self.assertEqual(run.call_count, 3)
        self.assertEqual(report["linked_count"], 1)
        self.assertEqual(report["ft_candidate_count"], 0)
        row = report["cases"][0]
        self.assertEqual(row["link_status"], "SAME_PROVIDER_FIXED_ID_UNAUTHENTICATED_LINK")
        self.assertEqual(row["raw_match_id"], "83212")
        self.assertEqual(row["raw_team_ids"], {"home": "40", "away": "7"})
        self.assertIsNone(row.get("score_ft_candidate"))
        self.assertFalse(report["independently_verified"])
        self.assertTrue(report["forecast_signature_reverified"])
        self.assert_held(report)
        self.assertEqual(row["raw_index"], 0)
        self.assertEqual(row["raw_member"], "openligadb.json")
        self.assertEqual(row["raw_sha256"], hashlib.sha256(
            (self.raw_dir / "openligadb.json").read_bytes()).hexdigest())
        self.assertEqual(row["paired_sha256"], hashlib.sha256(
            (self.proof / "paired.json").read_bytes()).hexdigest())
        self.assertEqual(row["pair_index"], 0)

    def test_saved_fake_proof_cannot_establish_raw_id_link(self):
        module = self.module()
        (self.proof / "provenance-audit.json").write_text(json.dumps({
            "audit_completed": True, "signature_identity_and_subjects_verified": True,
            "cases": [{"observed_before_recorded_kickoff": True}]}))
        with patch("forecast_provenance_audit.subprocess.run", return_value=
                   subprocess.CompletedProcess([], 1, b"[]", b"PRIVATE ERROR")) as run:
            report = module.audit_linkage(self.raw_dir, self.proof, **self.fixture.options)
        self.assertGreater(run.call_count, 0)
        self.assertFalse(report["audit_completed"])
        self.assertFalse(report["forecast_signature_reverified"])
        self.assertEqual(report["linked_count"], 0)
        self.assertNotIn("PRIVATE ERROR", json.dumps(report))
        self.assert_held(report)

    def test_finished_candidate_is_never_authenticated_or_eligible(self):
        self.finished()
        report, _ = self.run_linkage()
        self.assertTrue(report["audit_completed"])
        self.assertEqual(report["linked_count"], 1)
        self.assertEqual(report["ft_candidate_count"], 1)
        self.assertEqual(report["cases"][0]["score_ft_candidate"], [2, 1])
        self.assert_held(report)

    def test_replay_is_deterministic_and_reads_the_checked_raw_bytes(self):
        first, _ = self.run_linkage()
        second, _ = self.run_linkage()
        self.assertEqual(first, second)
        self.assertEqual(first["provenance_reference"]["subject_sha256"]["paired.json"],
                         first["paired_sha256"])

    def test_paired_replacement_after_current_audit_is_rejected(self):
        module = self.module()
        import forecast_provenance_audit
        real_audit = forecast_provenance_audit.audit

        def replace_after_audit(*args, **kwargs):
            result = real_audit(*args, **kwargs)
            self.fixture.pair["source_fixture_identity"]["match_id"] = "83213"
            self.fixture.write_inputs()
            return result

        stdout = json.dumps(self.fixture.stdout()).encode()
        with patch("forecast_provenance_audit.subprocess.run", return_value=
                   subprocess.CompletedProcess([], 0, stdout, b"")), patch(
                   "forecast_provenance_audit.audit", side_effect=replace_after_audit) as audit:
            report = module.audit_linkage(self.raw_dir, self.proof, **self.fixture.options)
        self.assertEqual(audit.call_count, 1)
        self.assertFalse(report["audit_completed"])
        self.assertFalse(report["forecast_signature_reverified"])
        self.assertEqual(report["reason"], "PAIRED_BYTES_CHANGED_AFTER_FRESH_AUDIT")
        self.assertEqual(report["linked_count"], 0)
        self.assert_held(report)

    def test_saved_verification_files_never_bypass_missing_current_cli(self):
        for name in ("shadow", "paired", "slate"):
            (self.proof / (name + ".verification.json")).write_text(json.dumps(self.fixture.stdout()))
        with patch("forecast_provenance_audit.subprocess.run", side_effect=FileNotFoundError()):
            report = self.module().audit_linkage(self.raw_dir, self.proof, **self.fixture.options)
        self.assertFalse(report["audit_completed"])
        self.assertFalse(report["forecast_signature_reverified"])
        self.assertEqual(report["linked_count"], 0)

    def test_raw_digest_tamper_rejected_then_recomputed_hash_stays_unauthenticated(self):
        self.finished()
        path = self.raw_dir / "openligadb.json"
        changed = path.read_bytes().replace(b'"pointsTeam1": 2', b'"pointsTeam1": 3')
        path.write_bytes(changed)
        report, _ = self.run_linkage()
        self.assertFalse(report["audit_completed"])
        self.assertEqual(report["reason"], "RAW_HASH_MISMATCH")
        self.assert_held(report)
        self.manifest["sources"][0]["raw_sha256"] = hashlib.sha256(changed).hexdigest()
        self.write_manifest()
        report, _ = self.run_linkage()
        self.assertTrue(report["audit_completed"])
        self.assertEqual(report["cases"][0]["score_ft_candidate"], [3, 1])
        self.assert_held(report)

    def test_raw_duplicate_ids_are_all_quarantined_even_with_different_teams(self):
        duplicate = copy.deepcopy(self.raw[0])
        duplicate["team1"]["teamName"] = "Other Club"
        self.raw.append(duplicate)
        self.write_raw()
        report, _ = self.run_linkage()
        self.assertTrue(report["audit_completed"])
        self.assertEqual(report["linked_count"], 0)
        self.assertEqual([row["reason"] for row in report["cases"]],
                         ["DUPLICATE_RAW_MATCH_ID"] * 2)

    def test_positive_integer_ids_cannot_be_bool_strings_floats_or_zero(self):
        original = copy.deepcopy(self.raw)
        for field in ("matchID", "home_id", "away_id"):
            for value in (True, False, "83212", 83212.0, 0, -1, None):
                with self.subTest(field=field, value=value):
                    self.raw = copy.deepcopy(original)
                    if field == "matchID": self.raw[0][field] = value
                    else: self.raw[0]["team1" if field == "home_id" else "team2"]["teamId"] = value
                    self.write_raw()
                    report, _ = self.run_linkage()
                    self.assertTrue(report["audit_completed"])
                    self.assertEqual(report["linked_count"], 0)
                    self.assertEqual(report["cases"][0]["link_status"], "QUARANTINED")
        self.raw = copy.deepcopy(original)
        self.raw[0]["team2"]["teamId"] = self.raw[0]["team1"]["teamId"]
        self.write_raw()
        report, _ = self.run_linkage()
        self.assertEqual(report["cases"][0]["reason"], "DUPLICATE_RAW_TEAM_ID")

    def test_raw_kickoff_requires_explicit_zero_offset_utc(self):
        for value in ("2026-10-18T15:30:00", "2026-10-18", "2026-10-18T16:30:00+01:00",
                      True, None, "not-a-time"):
            with self.subTest(value=value):
                self.raw[0]["matchDateTimeUTC"] = value
                self.write_raw()
                report, _ = self.run_linkage()
                self.assertEqual(report["linked_count"], 0)
                self.assertEqual(report["cases"][0]["reason"], "INVALID_RAW_KICKOFF_UTC")

    def test_capture_requires_explicit_zero_offset_utc(self):
        for value in ("2026-10-18T18:00:00", "2026-10-18T19:00:00+01:00", True, None):
            with self.subTest(value=value):
                self.manifest["captured_utc"] = value
                self.write_manifest()
                report, run = self.run_linkage()
                self.assertEqual(run.call_count, 3)
                self.assertFalse(report["audit_completed"])
                self.assertEqual(report["reason"], "INVALID_RAW_CAPTURE_UTC")
                self.assert_held(report)

    def test_capture_future_tolerance_is_chronology_only_and_original_claim_is_retained(self):
        self.manifest["captured_utc"] = "2026-10-18T14:05:01Z"
        self.write_manifest()
        report, _ = self.run_linkage()
        self.assertFalse(report["audit_completed"])
        self.assertEqual(report["reason"], "RAW_CAPTURE_CLAIM_IN_FUTURE")
        self.assertEqual(report["claimed_raw_capture_utc"], "2026-10-18T14:05:01Z")
        self.assertEqual(report["checked_utc"], "2026-10-18T14:00:00+00:00")
        self.assert_held(report)
        for claim in ("2026-10-18T14:05:00Z", "2026-10-17T10:00:00Z"):
            with self.subTest(claim=claim):
                self.manifest["captured_utc"] = claim
                self.write_manifest()
                report, _ = self.run_linkage()
                self.assertTrue(report["audit_completed"])
                self.assertEqual(report["linked_count"], 1)
                self.assertEqual(report["claimed_raw_capture_utc"], claim)
                self.assert_held(report)

    def test_exact_id_kickoff_and_names_conflict_without_fuzzy_fallback(self):
        for kind in ("kickoff", "home", "away", "wrong_id"):
            with self.subTest(kind=kind):
                self.raw[0].update(matchID=83212, matchDateTimeUTC=self.fixture.pair["kickoff_utc"])
                self.raw[0]["team1"]["teamName"] = "Bayern"
                self.raw[0]["team2"]["teamName"] = "Dortmund"
                if kind == "kickoff": self.raw[0]["matchDateTimeUTC"] = "2026-10-18T15:31:00Z"
                elif kind == "home": self.raw[0]["team1"]["teamName"] = "BAYERN"
                elif kind == "away": self.raw[0]["team2"]["teamName"] = "Borussia Dortmund"
                else: self.raw[0]["matchID"] = 83213
                self.write_raw()
                report, _ = self.run_linkage()
                self.assertEqual(report["linked_count"], 0)
                row = report["cases"][0]
                self.assertEqual(row["link_status"], "UNMATCHED" if kind == "wrong_id" else "CONFLICT")
                self.assertFalse(row["ft_candidate"])

    def test_legacy_and_unknown_provider_ids_are_not_backfilled(self):
        original = copy.deepcopy(self.fixture.pair)
        for kind in ("legacy", "untyped", "unknown_provider", "malformed", "promoted"):
            with self.subTest(kind=kind):
                self.fixture.pair.clear()
                self.fixture.pair.update(copy.deepcopy(original))
                if kind == "legacy":
                    for field in ("forecast_event_id", "source_fixture_identity", "source_fixture_identity_status"):
                        self.fixture.pair.pop(field)
                elif kind == "untyped":
                    self.fixture.pair.pop("source_fixture_identity")
                    self.fixture.pair.pop("source_fixture_identity_status")
                elif kind == "unknown_provider":
                    self.fixture.pair["source_fixture_identity"]["provider"] = "OtherProvider"
                elif kind == "malformed":
                    self.fixture.pair["source_fixture_identity"]["match_id"] = "083212"
                else: self.fixture.pair["eligible_for_model_scoring"] = True
                self.fixture.write_inputs()
                report, _ = self.run_linkage()
                self.assertTrue(report["audit_completed"])
                self.assertEqual(report["linked_count"], 0)
                self.assertEqual(len(report["sealed_exclusions"]), 1)
                self.assertNotIn("forecast_event_id", report["cases"][0])
                self.assert_held(report)

    def test_same_provider_id_claimed_for_different_sealed_fixtures_is_quarantined(self):
        pair = copy.deepcopy(self.fixture.pair)
        forecast = copy.deepcopy(self.fixture.forecast)
        pair.update(case_id="case-2", market_event_id="market-event-2", home="Other Home")
        forecast["home"] = "Other Home"
        self.fixture.shadow.update(predictions_count=2,
                                   predictions=[self.fixture.forecast, forecast])
        self.fixture.paired.update(matched_count=2, comparisons=[self.fixture.pair, pair])
        self.fixture.slate["point_in_time_market_pairs"] = 2
        self.fixture.write_inputs()
        report, _ = self.run_linkage()
        self.assertTrue(report["audit_completed"])
        self.assertEqual(report["linked_count"], 0)
        self.assertEqual(report["cases"][0]["reason"], "CONFLICTING_SEALED_PROVIDER_ID")

    def test_only_fresh_audit_observed_before_recorded_kickoff_cases_can_link(self):
        self.fixture.pair["kickoff_utc"] = self.fixture.forecast["kickoff_utc"] = "2026-10-18T13:50:00Z"
        self.raw[0]["matchDateTimeUTC"] = "2026-10-18T13:50:00Z"
        self.fixture.write_inputs()
        self.write_raw()
        report, _ = self.run_linkage()
        self.assertTrue(report["forecast_signature_reverified"])
        self.assertEqual(report["linked_count"], 0)
        self.assertEqual(report["sealed_exclusions"][0]["reason"],
                         "FORECAST_NOT_OBSERVED_BEFORE_RECORDED_KICKOFF")

    def test_truthy_finished_and_invalid_or_ambiguous_finals_refuse_ft(self):
        self.finished()
        original = copy.deepcopy(self.raw)
        for kind in ("truthy", "int_finished", "bool_goal", "float_goal", "negative_goal",
                     "too_many_goals", "float_type", "duplicate_final", "missing_final",
                     "missing_results", "capture_before", "malformed_results"):
            with self.subTest(kind=kind):
                self.raw = copy.deepcopy(original)
                self.manifest["captured_utc"] = "2026-10-18T18:00:00Z"
                row = self.raw[0]
                if kind == "truthy": row["matchIsFinished"] = "true"
                elif kind == "int_finished": row["matchIsFinished"] = 1
                elif kind == "bool_goal": row["matchResults"][0]["pointsTeam1"] = True
                elif kind == "float_goal": row["matchResults"][0]["pointsTeam1"] = 2.0
                elif kind == "negative_goal": row["matchResults"][0]["pointsTeam1"] = -1
                elif kind == "too_many_goals": row["matchResults"][0]["pointsTeam1"] = 31
                elif kind == "float_type": row["matchResults"][0]["resultTypeID"] = 2.0
                elif kind == "duplicate_final": row["matchResults"] *= 2
                elif kind == "missing_final": row["matchResults"][0]["resultTypeID"] = 1
                elif kind == "missing_results": row.pop("matchResults")
                elif kind == "capture_before": self.manifest["captured_utc"] = "2026-10-18T14:00:00Z"
                else: row["matchResults"] = [None]
                self.write_raw()
                report, _ = self.run_linkage()
                self.assertTrue(report["audit_completed"])
                self.assertEqual(report["ft_candidate_count"], 0)
                self.assertIsNone(report["cases"][0]["score_ft_candidate"])
                self.assert_held(report)

    def test_manifest_schema_safety_url_file_size_and_source_uniqueness(self):
        original = copy.deepcopy(self.manifest)
        changes = [("schema", "other"), ("status", "RESEARCH_ONLY"),
                   ("production_recommendations", "ENABLED"), ("independently_verified", True),
                   ("season_start", True), ("season_start", 1999), ("season_start", 2101),
                   ("source_url", "https://api.openligadb.de/getmatchdata/bl1/2025"),
                   ("raw_file", "../openligadb.json"), ("bytes", True), ("bytes", 1),
                   ("raw_sha256", "0" * 64), ("duplicate", None), ("status_source", "ERROR")]
        for field, value in changes:
            with self.subTest(field=field, value=value):
                self.manifest = copy.deepcopy(original)
                if field == "duplicate": self.manifest["sources"] *= 2
                elif field == "status_source": self.manifest["sources"][0]["status"] = value
                elif field in ("source_url", "raw_file", "bytes", "raw_sha256"):
                    self.manifest["sources"][0][field] = value
                else: self.manifest[field] = value
                self.write_manifest()
                report, _ = self.run_linkage()
                self.assertFalse(report["audit_completed"])
                self.assertEqual(report["linked_count"], 0)
                self.assert_held(report)

    def test_other_provider_url_and_digest_cannot_add_authentication(self):
        self.finished()
        self.manifest["sources"].append({
            "provider": "OpenFootball", "status": "FETCHED_UNVERIFIED",
            "source_url": "https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/de.1.json",
            "raw_file": "openfootball.json", "bytes": 2,
            "raw_sha256": hashlib.sha256(b"{}").hexdigest()})
        (self.raw_dir / "openfootball.json").write_bytes(b"{}")
        self.write_manifest()
        report, _ = self.run_linkage()
        self.assertEqual(report["ft_candidate_count"], 1)
        self.assert_held(report)

    def test_duplicate_keys_nonfinite_and_oversized_inputs_are_rejected(self):
        source = self.manifest["sources"][0]
        for body in (b'[{"matchID":83212,"matchID":83213}]', b'[NaN]', b'[Infinity]',
                     b'[1e999]', b'[', b'[]' + b' ' * 3_000_000,
                     json.dumps([{}] * 20_001).encode()):
            with self.subTest(prefix=body[:30], size=len(body)):
                (self.raw_dir / "openligadb.json").write_bytes(body)
                source.update(raw_sha256=hashlib.sha256(body).hexdigest(), bytes=len(body))
                self.write_manifest()
                report, _ = self.run_linkage()
                self.assertFalse(report["audit_completed"])
                self.assert_held(report)
        self.write_raw()
        valid = (self.raw_dir / "manifest.json").read_bytes()
        for body in (valid[:-1] + b',"status":"HOLD"}', valid + b' ' * 200_000):
            (self.raw_dir / "manifest.json").write_bytes(body)
            report, _ = self.run_linkage()
            self.assertFalse(report["audit_completed"])

    def test_symlink_and_nonregular_raw_files_rejected_without_blocking(self):
        path = self.raw_dir / "openligadb.json"
        body = path.read_bytes()
        outside = self.root / "outside.json"
        outside.write_bytes(body)
        path.unlink()
        path.symlink_to(outside)
        report, _ = self.run_linkage()
        self.assertFalse(report["audit_completed"])
        path.unlink()
        os.mkfifo(path)
        report, _ = self.run_linkage()
        self.assertFalse(report["audit_completed"])
        path.unlink()
        path.write_bytes(body)
        manifest_path = self.raw_dir / "manifest.json"
        outside.write_bytes(manifest_path.read_bytes())
        manifest_path.unlink()
        manifest_path.symlink_to(outside)
        report, _ = self.run_linkage()
        self.assertFalse(report["audit_completed"])

    def test_cli_completed_audit_exits_zero_but_report_stays_hold(self):
        stdout = json.dumps(self.fixture.stdout()).encode()
        output = self.root / "linkage.json"
        with patch("forecast_provenance_audit.subprocess.run", return_value=
                   subprocess.CompletedProcess([], 0, stdout, b"")):
            code = self.cli(output)
        self.assertEqual(code, 0)
        report = json.loads(output.read_bytes())
        self.assertTrue(report["audit_completed"])
        self.assert_held(report)

    def test_cli_failure_still_writes_safe_derived_report(self):
        output = self.root / "linkage.json"
        with patch("forecast_provenance_audit.subprocess.run", side_effect=FileNotFoundError()):
            code = self.cli(output)
        self.assertEqual(code, 1)
        report = json.loads(output.read_bytes())
        self.assertFalse(report["audit_completed"])
        self.assert_held(report)

    def test_cli_never_overwrites_inputs_symlinks_or_hardlink_aliases(self):
        target = self.raw_dir / "openligadb.json"
        before = target.read_bytes()
        symlink = self.root / "alias-symlink.json"
        symlink.symlink_to(target)
        hardlink = self.root / "alias-hardlink.json"
        os.link(target, hardlink)
        directory_alias = self.root / "directory-alias"
        directory_alias.symlink_to(self.proof, target_is_directory=True)
        stdout = json.dumps(self.fixture.stdout()).encode()
        for output in (target, self.raw_dir / "derived.json", self.proof / "paired.json",
                       self.proof / "derived.json", symlink, hardlink,
                       directory_alias / "derived.json"):
            with self.subTest(output=output), patch("forecast_provenance_audit.subprocess.run", return_value=
                       subprocess.CompletedProcess([], 0, stdout, b"")):
                self.assertEqual(self.cli(output), 1)
                self.assertEqual(target.read_bytes(), before)
        self.assertFalse((self.proof / "derived.json").exists())

    def test_symlink_parent_chains_are_rejected_for_inputs_and_outputs(self):
        module = self.module()
        raw_alias = self.root / "raw-alias"
        raw_alias.symlink_to(self.raw_dir, target_is_directory=True)
        proof_alias = self.root / "proof-alias"
        proof_alias.symlink_to(self.proof, target_is_directory=True)
        for raw_dir, proof in ((raw_alias, self.proof), (self.raw_dir, proof_alias),
                               (raw_alias / ".." / "raw", self.proof)):
            with self.subTest(raw_dir=raw_dir, proof=proof), patch(
                    "forecast_provenance_audit.audit") as audit:
                report = module.audit_linkage(raw_dir, proof, **self.fixture.options)
                self.assertFalse(report["audit_completed"])
                self.assertEqual(report["reason"], "SYMLINK_PATH_COMPONENT")
                audit.assert_not_called()  # Existing audit must never follow the parent alias.
        outside = self.root / "output-dir"
        outside.mkdir()
        output_alias = self.root / "output-alias"
        output_alias.symlink_to(outside, target_is_directory=True)
        stdout = json.dumps(self.fixture.stdout()).encode()
        with patch("forecast_provenance_audit.subprocess.run", return_value=
                   subprocess.CompletedProcess([], 0, stdout, b"")):
            self.assertEqual(self.cli(output_alias / "report.json"), 1)
        self.assertFalse((outside / "report.json").exists())

    def test_manifest_and_raw_directory_may_not_be_symlinks(self):
        module = self.module()
        alias = self.root / "raw-root-alias"
        alias.symlink_to(self.raw_dir, target_is_directory=True)
        report = module.audit_linkage(alias, self.proof, **self.fixture.options)
        self.assertFalse(report["audit_completed"])
        self.assertEqual(report["reason"], "SYMLINK_PATH_COMPONENT")

    def test_bounded_report_refuses_partial_success_output(self):
        with patch.object(self.module(), "MAX_OUTPUT_BYTES", 100):
            report, _ = self.run_linkage()
        self.assertFalse(report["audit_completed"])
        self.assertEqual(report["reason"], "OUTPUT_SIZE_LIMIT")
        self.assertEqual(report["cases"], [])


if __name__ == "__main__":
    unittest.main()
