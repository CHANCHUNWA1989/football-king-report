"""Synthetic shadow A native-id to genuine Penaltyblog API handoff guards."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ops.penaltyblog_a_shadow_native_handoff import link, main
from ops.tests.test_penaltyblog_a_dual_prematch_capture import Clock, A, CUT, KO, z

SHA = "e" * 64


def history():
    teams = ["101", "102", "103", "104"]
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    records = []
    for i in range(40):
        ko = start + timedelta(days=i)
        records.append({
            "source_namespace": "openligadb",
            "event_id": f"openligadb:{5000+i}",
            "league_id": "100",
            "home_team_id": teams[i % 4],
            "away_team_id": teams[(i + 1) % 4],
            "kickoff_utc": z(ko),
            "result_recorded_utc": z(ko + timedelta(hours=3)),
            "home_goals": i % 3,
            "away_goals": (i + 2) % 3,
        })
    return records


def shadow():
    started = A - timedelta(minutes=10)
    captured = A - timedelta(minutes=5)
    event = "openligadb:999999"
    native = {
        "schema": "football-king-native-fixture-input-observation-v1",
        "status": "UNAUTHENTICATED", "provider": "OpenLigaDB",
        "match_id": 999999, "home_team_id": 101, "away_team_id": 102,
        "league_id": 100, "league_shortcut": "bl1", "league_season": 2026,
        "source_response_sha256": SHA,
        "native_ids_from_same_response_as_gateway_fixture": True,
        "source_identity_authenticated": False,
        "source_capture_authenticated": False,
        "raw_input_durably_archived": False,
        "native_ids_used_as_model_features": False,
        "eligible_for_model_scoring": False,
    }
    return {
        "schema": "football-king-uncalibrated-shadow-1",
        "as_of_utc": z(A), "status": "SHADOW_ONLY", "season": "2026-27",
        "production_recommendations": "DISABLED",
        "independently_verified_results": False,
        "market_odds_available": False, "model_calibrated": False,
        "predictions_count": 1,
        "predictions": [{
            "league": "bundesliga", "event_id": event,
            "home": "Visible Team A", "away": "Visible Team B",
            "kickoff_utc": z(KO), "prediction_utc": z(A),
            "model": "poisson-shrinkage-unvalidated-v4.1",
            "p_home": .5, "p_draw": .3, "p_away": .2,
            "training_observations_sha256": "f" * 64,
            "native_fixture_input": native,
            "calibrated": False, "verified_market_odds": False,
            "production_recommendations": "DISABLED",
        }],
        "sources": [{
            "league": "bundesliga", "source": "OpenLigaDB",
            "status": "READY_RESEARCH", "season": "2026-27",
            "training_and_candidate_source_unverified": True,
            "source_response_sha256": SHA,
            "captured_utc": z(captured),
        }],
        "generation_clock": {
            "mode": "ACTUAL_BATCH_COMPUTATION_COMPLETION_UTC",
            "started_utc": z(started), "completed_utc": z(A),
            "sampled_clock_order_and_hk_day_valid": True,
            "reason": None, "excluded_predictions": 0,
            "enrichment_context_changed_leagues": [],
            "source_capture_or_actual_kickoff_authenticated": False,
        },
    }


class Grid:
    home_draw_away = [.5, .3, .2]


class FakeModel:
    calls = []
    def __init__(self, homes, aways, home_ids, away_ids):
        self.calls.append(("init", len(homes)))
        assert len(homes) == 40 and "101" in home_ids
    def fit(self):
        self.calls.append(("fit",))
    def predict(self, home, away, **kwargs):
        assert home == "101" and away == "102"
        assert kwargs == {"max_goals": 15, "normalize": True}
        self.calls.append(("predict",))
        return Grid()


FACTORIES = {"poisson": FakeModel, "dixon_coles": FakeModel}


class ShadowNativeHandoffTests(unittest.TestCase):
    def setUp(self):
        self.shadow = shadow()
        self.hist = history()
        self.clock = Clock()
        FakeModel.calls = []

    def go(self):
        return link(self.shadow, self.hist, event_id="openligadb:999999",
                    cutoff_utc=z(CUT), clock=self.clock,
                    model_factories=FACTORIES)

    def test_complete_local_technical_bridge_never_certifies(self):
        result = self.go()
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"],
                         "LOCAL_A_POISSON_DC_CAPTURE_NOT_EXTERNALLY_ATTESTED")
        self.assertTrue(result["shadow_a_native_identity_reused_without_mapping"])
        self.assertEqual(result["shadow_a_source_response_sha256_unattested"], SHA)
        self.assertFalse(result["shadow_source_response_bytes_durably_archived"])
        self.assertFalse(result["shadow_source_time_independently_attested"])
        self.assertFalse(result["shadow_producer_source_authenticated"])
        self.assertEqual(result["certified_prospective_samples"], 0)
        self.assertFalse(result["positive_ev_verified"])
        self.assertFalse(result["eligible_for_model_scoring"])
        self.assertEqual(len(result["unverified_triple_capture"]["challenger_observations"]), 2)
        self.assertEqual(result["unverified_triple_capture"]["home_team_id"], "101")
        self.assertEqual(result["unverified_triple_capture"]["away_team_id"], "102")
        self.assertEqual(result["unverified_triple_capture"]["league_id"], "100")
        self.assertEqual(len(FakeModel.calls), 6)

    def test_display_names_not_reinterpreted_as_native_ids(self):
        self.shadow["predictions"][0]["home"] = "Random unrelated words"
        self.assertEqual(self.go()["unverified_triple_capture"]["home_team_id"], "101")

    def test_missing_same_response_native_metadata_rejected(self):
        del self.shadow["predictions"][0]["native_fixture_input"]
        self.assertEqual(self.go()["reason"], "MISSING_TYPED_NATIVE_SOURCE_ID")
        self.assertEqual(FakeModel.calls, [])

    def test_replay_shadow_generation_rejected(self):
        del self.shadow["generation_clock"]
        self.assertEqual(self.go()["reason"], "REPLAY_OR_UNVERIFIED_GENERATION_CLOCK")

    def test_fake_clock_validation_rejected(self):
        self.shadow["generation_clock"]["sampled_clock_order_and_hk_day_valid"] = False
        self.assertEqual(self.go()["reason"], "REPLAY_OR_UNVERIFIED_GENERATION_CLOCK")

    def test_fake_authenticated_generation_rejected(self):
        self.shadow["generation_clock"]["source_capture_or_actual_kickoff_authenticated"] = True
        self.assertEqual(self.go()["reason"], "REPLAY_OR_UNVERIFIED_GENERATION_CLOCK")

    def test_prediction_not_equal_completion_rejected(self):
        self.shadow["predictions"][0]["prediction_utc"] = z(A - timedelta(seconds=1))
        self.assertEqual(self.go()["reason"], "INVALID_OR_MISSING_A_FORECAST_FIELDS")

    def test_shadow_as_of_not_equal_completion_rejected(self):
        self.shadow["as_of_utc"] = z(A - timedelta(seconds=1))
        self.assertEqual(self.go()["reason"], "SHADOW_BATCH_CLOCK_CONTRADICTION")

    def test_source_capture_after_completion_rejected(self):
        self.shadow["sources"][0]["captured_utc"] = z(A + timedelta(seconds=1))
        self.assertEqual(self.go()["reason"], "SOURCE_CAPTURE_NOT_WITHIN_A_GENERATION")

    def test_source_capture_before_start_rejected(self):
        self.shadow["sources"][0]["captured_utc"] = z(A - timedelta(hours=1))
        self.assertEqual(self.go()["reason"], "SOURCE_CAPTURE_NOT_WITHIN_A_GENERATION")

    def test_source_hash_mismatch_rejected(self):
        self.shadow["sources"][0]["source_response_sha256"] = "0" * 64
        self.assertEqual(self.go()["reason"], "SOURCE_RESPONSE_OR_LEAGUE_MISMATCH")

    def test_wrong_native_match_id_rejected(self):
        self.shadow["predictions"][0]["native_fixture_input"]["match_id"] = 999998
        self.assertEqual(self.go()["reason"], "INVALID_OR_SELF_CERTIFIED_NATIVE_EVIDENCE")

    def test_duplicate_shadow_prediction_event_rejected(self):
        self.shadow["predictions"].append(copy.deepcopy(self.shadow["predictions"][0]))
        self.shadow["predictions_count"] = 2
        self.assertEqual(self.go()["reason"], "MISSING_OR_AMBIGUOUS_A_FORECAST")

    def test_wrong_source_provider_rejected(self):
        self.shadow["sources"][0]["source"] = "Unknown"
        self.assertEqual(self.go()["reason"], "SOURCE_RESPONSE_OR_LEAGUE_MISMATCH")

    def test_source_not_ready_rejected(self):
        self.shadow["sources"][0]["status"] = "HOLD"
        self.assertEqual(self.go()["reason"], "SOURCE_RESPONSE_OR_LEAGUE_MISMATCH")

    def test_wrong_native_league_season_rejected(self):
        self.shadow["predictions"][0]["native_fixture_input"]["league_season"] = 2025
        self.assertEqual(self.go()["reason"], "NATIVE_LEAGUE_SEASON_MISMATCH")

    def test_wrong_native_team_bool_rejected(self):
        self.shadow["predictions"][0]["native_fixture_input"]["home_team_id"] = True
        self.assertEqual(self.go()["reason"], "INVALID_OR_SELF_CERTIFIED_NATIVE_EVIDENCE")

    def test_swapped_native_ids_never_corrected_by_display_names(self):
        # The caller can lie about the source record: this adapter cannot
        # authenticate it. It must NEVER substitute displayed team names.
        self.shadow["predictions"][0]["native_fixture_input"]["home_team_id"] = 102
        self.shadow["predictions"][0]["native_fixture_input"]["away_team_id"] = 101

        class ProbeModel(FakeModel):
            seen_targets = []

            def predict(self, home, away, **kwargs):
                self.seen_targets.append((home, away))
                return Grid()

        result = link(self.shadow, self.hist, event_id="openligadb:999999",
                      cutoff_utc=z(CUT), clock=self.clock,
                      model_factories={"poisson": ProbeModel, "dixon_coles": ProbeModel})
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["unverified_triple_capture"]["home_team_id"], "102")
        self.assertEqual(result["unverified_triple_capture"]["away_team_id"], "101")
        self.assertEqual(ProbeModel.seen_targets, [("102", "101"), ("102", "101")])
        self.assertFalse(result["original_a_source_authenticated"])

    def test_native_claiming_authentication_rejected(self):
        self.shadow["predictions"][0]["native_fixture_input"]["source_identity_authenticated"] = True
        self.assertEqual(self.go()["reason"], "INVALID_OR_SELF_CERTIFIED_NATIVE_EVIDENCE")

    def test_native_raw_archive_claim_rejected(self):
        self.shadow["predictions"][0]["native_fixture_input"]["raw_input_durably_archived"] = True
        self.assertEqual(self.go()["reason"], "INVALID_OR_SELF_CERTIFIED_NATIVE_EVIDENCE")

    def test_injected_model_result_rejected(self):
        self.shadow["predictions"][0]["native_fixture_input"]["result"] = [3, 1]
        self.assertEqual(self.go()["reason"], "MISSING_TYPED_NATIVE_SOURCE_ID")

    def test_original_model_changed_rejected(self):
        self.shadow["predictions"][0]["model"] = "pretend-penaltyblog"
        self.assertEqual(self.go()["reason"], "INVALID_OR_MISSING_A_FORECAST_FIELDS")

    def test_model_already_calibrated_claim_rejected(self):
        self.shadow["predictions"][0]["calibrated"] = True
        self.assertEqual(self.go()["reason"], "INVALID_OR_MISSING_A_FORECAST_FIELDS")

    def test_boolean_probability_rejected(self):
        self.shadow["predictions"][0]["p_home"] = True
        self.assertEqual(self.go()["reason"], "INVALID_OR_MISSING_A_FORECAST_FIELDS")

    def test_no_match_rejected(self):
        self.assertEqual(link(self.shadow, self.hist,
            event_id="openligadb:999998", cutoff_utc=z(CUT),
            clock=self.clock, model_factories=FACTORIES)["reason"],
            "MISSING_OR_AMBIGUOUS_A_FORECAST")

    def test_no_fabricating_native_id_from_arbitrary_event(self):
        self.assertEqual(link(self.shadow, self.hist,
            event_id="invented-fixture", cutoff_utc=z(CUT),
            clock=self.clock, model_factories=FACTORIES)["reason"],
            "INVALID_SHADOW_HANDOFF_INPUT")

    def test_future_training_result_rejected_before_model(self):
        self.hist[0]["result_recorded_utc"] = z(CUT)
        self.assertEqual(self.go()["reason"], "LOOKAHEAD_OR_UNAVAILABLE_RESULT")
        self.assertEqual(FakeModel.calls, [])

    def test_cross_provider_history_rejected(self):
        self.hist[0]["source_namespace"] = "other"
        self.assertEqual(self.go()["reason"], "CROSS_SOURCE_OR_LEAGUE_MISMATCH")

    def test_too_late_cutoff_rejected(self):
        self.assertEqual(link(self.shadow, self.hist,
            event_id="openligadb:999999", cutoff_utc=z(KO),
            clock=self.clock, model_factories=FACTORIES)["reason"],
            "INVALID_LATER_DECISION_CUTOFF")

    def test_local_second_model_misses_cutoff_blocks_entire_handoff(self):
        self.clock = Clock([A + timedelta(minutes=5), A + timedelta(minutes=6),
                            CUT + timedelta(seconds=1)])
        result = self.go()
        self.assertEqual(result["reason"], "MODEL_EXECUTION_CROSSED_PREMATCH_WINDOW")
        self.assertNotIn("unverified_triple_capture", result)
        self.assertFalse(result["shadow_a_native_identity_reused_without_mapping"])

    def test_no_private_output_on_invalid_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            s, h, o = (Path(tmp) / name for name in ("shadow.json", "hist.json", "out.json"))
            s.write_text(json.dumps(self.shadow), encoding="utf-8")
            h.write_text(json.dumps(self.hist), encoding="utf-8")
            self.assertEqual(main(["--shadow", str(s), "--history", str(h),
                "--event-id", "openligadb:999999",
                "--decision-cutoff-utc", "2026-12-01T00:00:00Z",
                "--output", str(o)]), 1)
            self.assertFalse(o.exists())

    def test_private_output_no_overwrite_even_on_mock_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            s, h, o = (Path(tmp) / name for name in ("shadow.json", "hist.json", "out.json"))
            s.write_text(json.dumps(self.shadow), encoding="utf-8")
            h.write_text(json.dumps(self.hist), encoding="utf-8")
            o.write_bytes(b"protected")
            safe = {"status": "HOLD", "reason": "LOCAL_A_POISSON_DC_CAPTURE_NOT_EXTERNALLY_ATTESTED",
                    "unverified_triple_capture": {"synthetic": True},
                    "production_recommendations": "DISABLED"}
            with patch("ops.penaltyblog_a_shadow_native_handoff.link", return_value=safe):
                self.assertEqual(main(["--shadow", str(s), "--history", str(h),
                    "--event-id", "openligadb:999999",
                    "--decision-cutoff-utc", z(CUT), "--output", str(o)]), 1)
            self.assertEqual(o.read_bytes(), b"protected")

    def test_symlink_shadow_input_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real.json"
            shadow_link = Path(tmp) / "link.json"
            h = Path(tmp) / "hist.json"
            out = Path(tmp) / "out.json"
            real.write_text(json.dumps(self.shadow), encoding="utf-8")
            h.write_text(json.dumps(self.hist), encoding="utf-8")
            shadow_link.symlink_to(real)
            self.assertEqual(main(["--shadow", str(shadow_link), "--history", str(h),
                "--event-id", "openligadb:999999",
                "--decision-cutoff-utc", z(CUT), "--output", str(out)]), 1)
            self.assertFalse(out.exists())

    def test_output_input_alias_blocks_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            s, h = Path(tmp) / "shadow.json", Path(tmp) / "hist.json"
            s.write_text(json.dumps(self.shadow), encoding="utf-8")
            h.write_text(json.dumps(self.hist), encoding="utf-8")
            copy_content = s.read_bytes()
            self.assertEqual(main(["--shadow", str(s), "--history", str(h),
                "--event-id", "openligadb:999999",
                "--decision-cutoff-utc", z(CUT), "--output", str(s)]), 1)
            self.assertEqual(s.read_bytes(), copy_content)


if __name__ == "__main__":
    unittest.main()
