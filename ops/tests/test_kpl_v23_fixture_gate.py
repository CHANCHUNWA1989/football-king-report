"""KPL V23 future-source dossier checks; NO real KPL forecast is published."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from research.kpl_v23_fixture_gate import (
    load_fixture_dossier, screen_fixture_dossier, screen_fixture_file,
)

FIXTURE_FILE = (
    Path(__file__).resolve().parents[2] /
    "research" / "kpl_v23_20261104_ttg_wolves_fixture.json")
REVIEW_CLOCK = "2026-11-03T15:03:00Z"


class KPLV23FixtureTests(unittest.TestCase):
    def setUp(self):
        self.fixture = load_fixture_dossier(FIXTURE_FILE)

    def check(self, candidate=None, *, now=REVIEW_CLOCK):
        return screen_fixture_dossier(
            self.fixture if candidate is None else candidate, now=now)

    def test_real_upcoming_corroborated_fixture_is_hold_not_a_pick(self):
        result = self.check()
        self.assertTrue(result["technical_schedule_claims_consistent"], result)
        self.assertEqual(result["fixture_key"],
                         "kpl-2026-11-04-ttg-wolves-research-candidate")
        self.assertEqual(result["scheduled_session_at"],
                         "2026-11-04T10:00:00Z")
        self.assertEqual(result["source_claim_count"], 3)
        self.assertEqual(result["decision"], "HOLD")
        self.assertIsNone(result["probability_a"])
        self.assertEqual(result["status"], "HOLD")
        self.assertFalse(result["trial_started"])
        self.assertFalse(result["v20_registration_performed"])
        self.assertFalse(result["official_fixture_id_authenticated"])
        self.assertFalse(result["bp_complete_and_authenticated"])
        self.assertFalse(result["real_kpl_prediction_accuracy_verified"])
        self.assertFalse(result["positive_ev_verified"])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["live_execution_allowed"])

    def test_candidate_file_is_parseable_and_contains_no_outcome_or_odds(self):
        self.assertNotIn("winner_team_id", self.fixture)
        self.assertNotIn("result", self.fixture)
        self.assertNotIn("odds", self.fixture)
        self.assertEqual(self.fixture["decision"], "HOLD")
        self.assertIsNone(self.fixture["probability_a"])

    def test_read_path_and_no_background_registration(self):
        result = screen_fixture_file(FIXTURE_FILE, now=REVIEW_CLOCK)
        self.assertTrue(result["technical_schedule_claims_consistent"])
        self.assertFalse(result["trial_started"])

    def test_start_date_is_not_precise_map_one_start(self):
        r = self.check()
        self.assertFalse(r["first_map_kickoff_time_verified"])
        self.assertIn(
            "NO_VERIFIED_FIRST_MAP_KICKOFF_BP_OR_CALIBRATED_PROBABILITY",
            r["reasons"])

    def test_after_session_starts_cannot_pretend_future(self):
        r = self.check(now="2026-11-04T10:00:01Z")
        self.assertFalse(r["technical_schedule_claims_consistent"])
        self.assertIn("SESSION_ALREADY_STARTED_OR_IN_PAST", r["reasons"])

    def test_equal_to_session_start_rejected(self):
        self.assertIn(
            "SESSION_ALREADY_STARTED_OR_IN_PAST",
            self.check(now="2026-11-04T10:00:00Z")["reasons"])

    def test_three_sources_do_not_authenticate_themselves(self):
        r = self.check()
        self.assertFalse(r["publisher_identity_independently_authenticated"])
        self.assertFalse(r["independent_source_capture_time_verified"])
        self.assertFalse(r["rights_for_real_data_verified"])
        self.assertFalse(r["tsa_timestamp_independently_witnessed"])

    def test_unverified_odds_and_game_winner_fields_forbidden(self):
        candidate = copy.deepcopy(self.fixture)
        candidate["winner_team_id"] = "guangzhou-ttg"
        self.assertIn(
            "INVALID_OR_INCOMPLETE_DOSSIER_SCHEMA",
            self.check(candidate)["reasons"])

    def test_unverified_model_probability_forbidden(self):
        candidate = copy.deepcopy(self.fixture)
        candidate["probability_a"] = 0.545
        self.assertIn(
            "PREDICTION_OR_AUTHORITY_PREMATURELY_ASSERTED",
            self.check(candidate)["reasons"])

    def test_no_false_calibrated_model_claim(self):
        candidate = copy.deepcopy(self.fixture)
        candidate["model_status"] = "CALIBRATED"
        self.assertIn(
            "PREDICTION_OR_AUTHORITY_PREMATURELY_ASSERTED",
            self.check(candidate)["reasons"])

    def test_no_unverified_official_fixture_id(self):
        candidate = copy.deepcopy(self.fixture)
        candidate["official_fixture_id"] = "invented-match-id"
        self.assertIn(
            "PREDICTION_OR_AUTHORITY_PREMATURELY_ASSERTED",
            self.check(candidate)["reasons"])

    def test_cannot_claim_actual_v20_trial_registered(self):
        candidate = copy.deepcopy(self.fixture)
        candidate["trial_registration_status"] = "REGISTERED"
        self.assertIn(
            "PREDICTION_OR_AUTHORITY_PREMATURELY_ASSERTED",
            self.check(candidate)["reasons"])

    def test_missing_matchup_announcement_forces_hold(self):
        candidate = copy.deepcopy(self.fixture)
        candidate["observations"] = [
            r for r in candidate["observations"]
            if r["role"] != "TEAM_MATCHUP_ANNOUNCEMENT_CLAIM"]
        candidate["observations"].append({
            **candidate["observations"][-1],
            "source_id": "different-same-role",
            "source_url": "https://another.example.com/schedule"})
        r = self.check(candidate)
        self.assertIn("MISSING_ROLE_OR_NONINDEPENDENT_MATCHUP_HOSTS",
                      r["reasons"])

    def test_league_calendar_cannot_claim_it_verified_teams(self):
        candidate = copy.deepcopy(self.fixture)
        candidate["observations"][0]["teams"] = candidate["teams"]
        self.assertIn("SESSION_ONLY_SOURCE_CLAIMS_TEAM_MATCHUP",
                      self.check(candidate)["reasons"])

    def test_wrong_game_time_in_any_source_rejected(self):
        candidate = copy.deepcopy(self.fixture)
        candidate["observations"][1]["scheduled_session_at"] = (
            "2026-11-04T11:00:00Z")
        self.assertIn("CONFLICTING_OR_FUTURE_SOURCE_CLAIM",
                      self.check(candidate)["reasons"])

    def test_wrong_matchup_in_any_source_rejected(self):
        candidate = copy.deepcopy(self.fixture)
        candidate["observations"][2]["teams"] = [
            "guangzhou-ttg", "wrong-team"]
        self.assertIn("CONFLICTING_MATCHUP_IDENTITIES",
                      self.check(candidate)["reasons"])

    def test_swapped_pair_order_still_identifies_same_game(self):
        candidate = copy.deepcopy(self.fixture)
        candidate["observations"][1]["teams"].reverse()
        self.assertTrue(
            self.check(candidate)["technical_schedule_claims_consistent"])

    def test_duplicate_source_url_rejected(self):
        candidate = copy.deepcopy(self.fixture)
        candidate["observations"][2]["source_url"] = (
            candidate["observations"][1]["source_url"])
        self.assertIn("DUPLICATE_FIXTURE_SOURCE",
                      self.check(candidate)["reasons"])

    def test_same_hostnames_for_all_pair_claims_fail_independence(self):
        candidate = copy.deepcopy(self.fixture)
        candidate["observations"][2]["source_url"] = (
            "https://www.sina.cn/schedule/independent-looking")
        self.assertIn("MISSING_ROLE_OR_NONINDEPENDENT_MATCHUP_HOSTS",
                      self.check(candidate)["reasons"])

    def test_claimed_posting_after_review_clock_rejected(self):
        candidate = copy.deepcopy(self.fixture)
        candidate["observations"][1]["published_at"] = (
            "2026-11-03T22:00:00Z")
        self.assertIn("CONFLICTING_OR_FUTURE_SOURCE_CLAIM",
                      self.check(candidate)["reasons"])

    def test_unknown_published_at_does_not_become_authenticated(self):
        candidate = copy.deepcopy(self.fixture)
        self.assertIsNone(candidate["observations"][2]["published_at"])
        r = self.check(candidate)
        self.assertTrue(r["technical_schedule_claims_consistent"])
        self.assertFalse(r["independent_source_capture_time_verified"])

    def test_forged_independent_authentication_boolean_rejected(self):
        candidate = copy.deepcopy(self.fixture)
        candidate["observations"][2]["independently_authenticated"] = True
        self.assertIn("SELF_ASSERTED_INDEPENDENT_AUTHENTICATION",
                      self.check(candidate)["reasons"])

    def test_http_or_credentials_in_source_url_rejected(self):
        for url in ("http://m.wanplus.cn/schedule/94809.html",
                    "https://bad:password@m.wanplus.cn/schedule/94809.html"):
            with self.subTest(url=url):
                candidate = copy.deepcopy(self.fixture)
                candidate["observations"][2]["source_url"] = url
                self.assertIn("INVALID_SOURCE_URL_OR_CLOCK",
                              self.check(candidate)["reasons"])

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.json"
            path.write_text('{"fixture_key":"one","fixture_key":"two"}')
            self.assertIn(
                "INVALID_OR_UNREADABLE_FIXTURE_DOSSIER",
                screen_fixture_file(path, now=REVIEW_CLOCK)["reasons"])

    def test_missing_file_fails_closed(self):
        result = screen_fixture_file(
            "/unfindable-v23-research-fixture-dossier.json", now=REVIEW_CLOCK)
        self.assertIn("INVALID_OR_UNREADABLE_FIXTURE_DOSSIER",
                      result["reasons"])

    def test_extra_unsupported_source_evidence_rejected(self):
        candidate = copy.deepcopy(self.fixture)
        candidate["observations"][1]["official_verification"] = True
        self.assertIn("INVALID_SOURCE_OBSERVATION_SCHEMA",
                      self.check(candidate)["reasons"])

    def test_nonfinite_json_values_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "nan.json"
            path.write_text('{"probability_a":NaN}')
            self.assertIn(
                "INVALID_OR_UNREADABLE_FIXTURE_DOSSIER",
                screen_fixture_file(path, now=REVIEW_CLOCK)["reasons"])


if __name__ == "__main__":
    unittest.main()
