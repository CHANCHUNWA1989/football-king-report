"""V24 real fixture, synthetic fake-data attack tests. Never register a trial."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.kpl_v23_fixture_gate import load_fixture_dossier
from research.kpl_v24_trial_activation_gate import (
    audit_trial_activation, audit_trial_activation_files,
)

ROOT = Path(__file__).resolve().parents[2] / "research"
FIXTURE = ROOT / "kpl_v23_20261104_ttg_wolves_fixture.json"
READINESS = ROOT / "kpl_v24_20261104_ttg_wolves_readiness.json"
PREVIEW_CLOCK = "2026-11-03T15:05:00Z"
BEFORE_BP_CLOCK = "2026-11-04T09:45:00Z"
ROLES = ["CLASH", "JUNGLE", "MID", "FARM", "ROAM"]
SERIES = "synthetic-only-series-for-gate-tests"


def claimed_complete(original):
    """Fake complete evidence: STRUCTURALLY coherent, NOT truly authenticated."""
    payload = copy.deepcopy(original)
    payload["official_series_id"] = SERIES
    payload["verified_first_map_start_at"] = "2026-11-04T10:30:00Z"
    payload["match_specific_lineups"] = []
    for team, opponent in (
        ("guangzhou-ttg", "chongqing-wolves"),
        ("chongqing-wolves", "guangzhou-ttg"),
    ):
        payload["match_specific_lineups"].append({
            "fixture_key": payload["fixture_key"],
            "official_series_id": SERIES,
            "match_date": "2026-11-04",
            "team_id": team, "opponent_id": opponent,
            "published_at": "2026-11-04T02:00:00Z",
            "source_url": f"https://fixture.example.test/{team}/lineup",
            "source_kind": "MATCH_SPECIFIC_OFFICIAL_LINEUP_CLAIM",
            "players": [
                {"role": role, "player_id": f"{team}-{i}"}
                for i, role in enumerate(ROLES)
            ],
        })
    teams = payload["team_ids"]
    payload["match_specific_game_one_bp"] = {
        "fixture_key": payload["fixture_key"],
        "official_series_id": SERIES,
        "game_number": 1,
        "team_ids": teams,
        "bp_locked_at": "2026-11-04T09:30:00Z",
        "captured_at": "2026-11-04T09:35:00Z",
        "source_url": "https://fixture.example.test/bp",
        "source_kind": "FIRST_MAP_LOCKED_BP_CLAIM",
        "bans_by_team": {
            team: [f"{team}-ban-{i}" for i in range(5)] for team in teams},
        "picks_by_team": {
            team: [f"{team}-pick-{i}" for i in range(5)] for team in teams},
    }
    payload["model_holdout_evidence"] = {
        "model_version": "fake-model-only", "model_frozen_at": "2026-11-03T09:00:00Z",
        "evaluation_phase": "BP_LOCKED",
        "independent_bo_series": 50, "out_of_sample_maps": 180,
        "brier_gain": 0.02, "clustered_gain_lower_bound": 0.002,
        "source_id": "fabricated-evaluation",
    }
    payload["rights_evidence"] = {
        "provider_id": "fabricated-provider",
        "grant_document_sha256": "a" * 64,
        "research_use_allowed": True,
        "grant_observed_at": "2026-11-01T02:00:00Z",
        "grant_expires_at": "2026-11-30T00:00:00Z",
    }
    return payload


class TestKPLV24TrialActivation(unittest.TestCase):
    def setUp(self):
        self.fixture = load_fixture_dossier(FIXTURE)
        self.readiness = json.loads(READINESS.read_text())

    def audit(self, readiness=None, *, now=PREVIEW_CLOCK, fixture=None, **kwargs):
        return audit_trial_activation(
            self.fixture if fixture is None else fixture,
            self.readiness if readiness is None else readiness,
            now=now, **kwargs)

    def test_nov04_fixture_stays_hold_without_actual_bp_lineup_tsa(self):
        r = self.audit()
        self.assertEqual(r["status"], "HOLD")
        self.assertIsNone(r["probability_a"])
        self.assertEqual(r["decision"], "HOLD")
        self.assertTrue(r["fixture_source_claims_consistent"], r)
        self.assertTrue(r["previous_lineups_excluded_from_current_match"])
        self.assertFalse(r["match_lineup_structure_valid"])
        self.assertFalse(r["first_map_bp_structure_valid"])
        self.assertFalse(r["real_kpl_accuracy_verified"])
        self.assertFalse(r["activation_allowed"])
        self.assertFalse(r["registration_created_by_gate"])
        self.assertEqual(r["real_kpl_forecast_count_created"], 0)
        self.assertFalse(r["live_execution_allowed"])
        self.assertEqual(r["production_recommendations"], "DISABLED")

    def test_exact_real_wolves_nov03_source_replaces_syndicated_page(self):
        notice = next(o for o in self.fixture["observations"]
                      if o["role"] == "TEAM_MATCHUP_ANNOUNCEMENT_CLAIM")
        self.assertEqual(
            notice["source_url"],
            "https://3g.sina.com.cn/news/detail/5361259081630430.html")
        self.assertEqual(notice["published_at"], "2026-11-03T12:00:35Z")

    def test_nov02_wolves_vs_jdg_lineup_not_ttg_wolves(self):
        older = self.readiness["previous_match_lineup_context"][0]
        self.assertEqual(older["match_date"], "2026-11-02")
        self.assertEqual(older["opponent_id"], "beijing-jdg")
        self.assertFalse(older["usable_for_current_match"])
        r = self.audit()
        self.assertIn("NO_TWO_MATCH_SPECIFIC_OFFICIAL_LINEUP_CLAIMS", r["reasons"])

    def test_claiming_old_lineup_as_current_fails(self):
        fake = claimed_complete(self.readiness)
        fake["match_specific_lineups"][1]["match_date"] = "2026-11-02"
        r = self.audit(fake, now=BEFORE_BP_CLOCK)
        self.assertFalse(r["match_lineup_structure_valid"])
        self.assertIn("NO_TWO_MATCH_SPECIFIC_OFFICIAL_LINEUP_CLAIMS", r["reasons"])

    def test_substituting_old_jdg_opponent_fails(self):
        fake = claimed_complete(self.readiness)
        fake["match_specific_lineups"][1]["opponent_id"] = "beijing-jdg"
        self.assertFalse(self.audit(fake, now=BEFORE_BP_CLOCK)[
            "match_lineup_structure_valid"])

    def test_wrong_official_series_id_in_lineup_fails(self):
        fake = claimed_complete(self.readiness)
        fake["match_specific_lineups"][0]["official_series_id"] = "other-series"
        self.assertFalse(self.audit(fake, now=BEFORE_BP_CLOCK)[
            "match_lineup_structure_valid"])

    def test_wrong_fixture_key_in_bp_fails(self):
        fake = claimed_complete(self.readiness)
        fake["match_specific_game_one_bp"]["fixture_key"] = "other-event"
        r = self.audit(fake, now=BEFORE_BP_CLOCK)
        self.assertFalse(r["first_map_bp_structure_valid"])

    def test_game_two_bp_cannot_stand_in_for_game_one(self):
        fake = claimed_complete(self.readiness)
        fake["match_specific_game_one_bp"]["game_number"] = 2
        self.assertFalse(self.audit(fake, now=BEFORE_BP_CLOCK)[
            "first_map_bp_structure_valid"])

    def test_september_summer_final_bp_cannot_be_reused(self):
        fake = claimed_complete(self.readiness)
        fake["match_specific_game_one_bp"]["bp_locked_at"] = (
            "2026-09-12T10:00:00Z")
        self.assertIn(
            "FIRST_MAP_BP_NOT_LOCKED_FOR_SAME_FIXTURE_AND_TIME",
            self.audit(fake, now=BEFORE_BP_CLOCK)["reasons"])

    def test_stale_first_map_start_before_official_session_fails(self):
        fake = claimed_complete(self.readiness)
        fake["verified_first_map_start_at"] = "2026-11-04T09:00:00Z"
        r = self.audit(fake, now=BEFORE_BP_CLOCK)
        self.assertIn("EXACT_FIRST_MAP_KICKOFF_UNVERIFIED", r["reasons"])

    def test_bp_claim_captured_after_review_fails(self):
        fake = claimed_complete(self.readiness)
        fake["match_specific_game_one_bp"]["captured_at"] = (
            "2026-11-04T10:00:00Z")
        self.assertFalse(self.audit(fake, now=BEFORE_BP_CLOCK)[
            "first_map_bp_structure_valid"])

    def test_fake_duplicate_hero_picks_cannot_be_full_bp(self):
        fake = claimed_complete(self.readiness)
        ttg, wolves = fake["team_ids"]
        fake["match_specific_game_one_bp"]["picks_by_team"][ttg][0] = (
            fake["match_specific_game_one_bp"]["picks_by_team"][wolves][0])
        self.assertFalse(self.audit(fake, now=BEFORE_BP_CLOCK)[
            "first_map_bp_structure_valid"])

    def test_claiming_official_start_time_alone_does_not_activate(self):
        fake = copy.deepcopy(self.readiness)
        fake["official_series_id"] = SERIES
        fake["verified_first_map_start_at"] = "2026-11-04T10:30:00Z"
        r = self.audit(fake)
        self.assertFalse(r["activation_allowed"])
        self.assertFalse(r["actual_g1_kickoff_independently_authenticated"])

    def test_even_complete_fabricated_data_is_never_independently_proven(self):
        fake = claimed_complete(self.readiness)
        r = self.audit(fake, now=BEFORE_BP_CLOCK)
        self.assertTrue(r["structural_inputs_complete"], r)
        self.assertFalse(r["official_series_id_independently_authenticated"])
        self.assertFalse(r["actual_usage_rights_independently_verified"])
        self.assertFalse(r["real_kpl_model_calibration_verified"])
        self.assertFalse(r["activation_allowed"])
        self.assertFalse(r["registration_created_by_gate"])
        self.assertEqual(r["status"], "HOLD")

    def test_fake_independent_tsa_boolean_does_not_prove_trust(self):
        fake = claimed_complete(self.readiness)
        fake["independent_tsa_evidence"] = {"verified": True}
        r = self.audit(fake, now=BEFORE_BP_CLOCK)
        self.assertIn("SELF_ASSERTED_TSA_TRUST_NOT_ACCEPTED", r["reasons"])
        self.assertFalse(r["independent_tsa_authority_verified"])

    def test_fake_trial_registration_status_does_not_prove_registration(self):
        fake = claimed_complete(self.readiness)
        fake["v20_trial_registration"] = {"created": True, "id": "made-up"}
        r = self.audit(fake, now=BEFORE_BP_CLOCK)
        self.assertIn("SELF_ASSERTED_TRIAL_REGISTRATION_NOT_ACCEPTED",
                      r["reasons"])
        self.assertFalse(r["registration_created_by_gate"])

    def test_invalid_existing_trial_receipts_are_checked_using_v22(self):
        with tempfile.TemporaryDirectory() as folder:
            r = self.audit(existing_trial_dir=folder,
                           timestamp_receipts=[], tsa_trust={})
        self.assertIn("V22_TIMESTAMP_CRYPTO_COVERAGE_FAILED", r["reasons"])
        self.assertFalse(r["tsa_crypto_locally_consistent"])
        self.assertFalse(r["activation_allowed"])

    def test_no_synthetic_tsa_result_can_be_promoted(self):
        fake = claimed_complete(self.readiness)
        with patch(
            "research.kpl_v24_trial_activation_gate.audit_shadow_timestamp_bundle",
            return_value={
                "all_manifest_and_recorded_decisions_timestamp_bound": True,
                "cryptographically_consistent_record_count": 5,
                "revocation_status_completely_authenticated": False,
            }
        ):
            r = self.audit(fake, now=BEFORE_BP_CLOCK,
                           existing_trial_dir="synthetic",
                           timestamp_receipts=[{"made_up": True}],
                           tsa_trust={"synthetic": True})
        self.assertTrue(r["tsa_crypto_locally_consistent"])
        self.assertEqual(r["locally_witnessed_record_count"], 5)
        self.assertFalse(r["independent_tsa_authority_verified"])
        self.assertFalse(r["activation_allowed"])

    def test_gate_never_invokes_v20_registration_or_prediction(self):
        with patch("research.kpl_v20_shadow_trial.register_shadow_trial",
                   side_effect=AssertionError("must not register")):
            r = self.audit()
        self.assertFalse(r["registration_created_by_gate"])
        self.assertFalse(r["actual_pregame_prediction_exists"])

    def test_after_nov4_session_starts_is_not_pre_game(self):
        r = self.audit(now="2026-11-04T10:00:00Z")
        self.assertIn("REVIEW_CLOCK_AFTER_SESSION_OR_IN_FUTURE", r["reasons"])
        self.assertFalse(r["activation_allowed"])

    def test_future_dated_review_self_claim_rejected(self):
        fake = copy.deepcopy(self.readiness)
        fake["reviewed_at"] = "2026-11-04T09:00:00Z"
        r = self.audit(fake)
        self.assertIn("REVIEW_CLOCK_AFTER_SESSION_OR_IN_FUTURE", r["reasons"])

    def test_corrupt_fixture_source_time_blocks(self):
        fixture = copy.deepcopy(self.fixture)
        fixture["observations"][1]["scheduled_session_at"] = (
            "2026-11-05T10:00:00Z")
        r = self.audit(fixture=fixture)
        self.assertIn("FIXTURE_SOURCE_DOSSIER_NOT_READY", r["reasons"])

    def test_mismatched_teams_blocks_gate(self):
        fake = copy.deepcopy(self.readiness)
        fake["team_ids"] = ["guangzhou-ttg", "beijing-jdg"]
        self.assertIn("FIXTURE_IDENTITY_OR_STAGE_SCHEMA_MISMATCH",
                      self.audit(fake)["reasons"])

    def test_unverified_model_unsupported_phase_fails(self):
        fake = claimed_complete(self.readiness)
        fake["model_holdout_evidence"]["evaluation_phase"] = "PRE_GAME"
        r = self.audit(fake, now=BEFORE_BP_CLOCK)
        self.assertIn("REAL_KPL_SAME_PHASE_HOLDOUT_CALIBRATION_MISSING",
                      r["reasons"])

    def test_fake_high_brier_gain_not_enough_without_cluster_evidence(self):
        fake = claimed_complete(self.readiness)
        fake["model_holdout_evidence"]["clustered_gain_lower_bound"] = -0.01
        r = self.audit(fake, now=BEFORE_BP_CLOCK)
        self.assertFalse(r["model_holdout_fields_valid"])

    def test_grant_expired_before_session_fails(self):
        fake = claimed_complete(self.readiness)
        fake["rights_evidence"]["grant_expires_at"] = "2026-11-03T18:00:00Z"
        r = self.audit(fake, now=BEFORE_BP_CLOCK)
        self.assertFalse(r["rights_documentary_fields_valid"])

    def test_fake_document_hash_is_not_actual_rights(self):
        fake = claimed_complete(self.readiness)
        r = self.audit(fake, now=BEFORE_BP_CLOCK)
        self.assertTrue(r["rights_documentary_fields_valid"])
        self.assertFalse(r["actual_usage_rights_independently_verified"])

    def test_unknown_previous_lineup_marked_current_fails(self):
        fake = copy.deepcopy(self.readiness)
        fake["previous_match_lineup_context"][0][
            "usable_for_current_match"] = True
        r = self.audit(fake)
        self.assertIn(
            "PREVIOUS_MATCH_LINEUP_CONTEXT_INVALID_OR_NOT_EXCLUDED",
            r["reasons"])

    def test_readiness_file_load_does_not_start_trial(self):
        r = audit_trial_activation_files(
            FIXTURE, READINESS, now=PREVIEW_CLOCK)
        self.assertEqual(r["status"], "HOLD")
        self.assertFalse(r["registration_created_by_gate"])
        self.assertFalse(r["activation_allowed"])

    def test_duplicate_json_keys_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "bad.json"
            p.write_text('{"fixture_key":"x","fixture_key":"y"}')
            r = audit_trial_activation_files(FIXTURE, p, now=PREVIEW_CLOCK)
        self.assertIn("INVALID_OR_UNREADABLE_READINESS_FILES", r["reasons"])

    def test_invalid_readiness_schema_and_sneaked_odds_fail(self):
        fake = copy.deepcopy(self.readiness)
        fake["bookmaker_odds"] = {"ttg": 1.3}
        r = self.audit(fake)
        self.assertIn("INVALID_OR_INCOMPLETE_READINESS_SCHEMA", r["reasons"])
        self.assertIsNone(r["probability_a"])

    def test_incomplete_tsa_args_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            r = self.audit(existing_trial_dir=folder)
        self.assertIn("INCOMPLETE_TSA_RAW_EVIDENCE_ARGUMENTS", r["reasons"])
        self.assertFalse(r["activation_allowed"])

    def test_no_source_data_network_calls(self):
        self.assertFalse(self.audit()["actual_pregame_prediction_exists"])


if __name__ == "__main__":
    unittest.main()
