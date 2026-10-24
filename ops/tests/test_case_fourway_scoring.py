"""Pure scoring policy tests; synthetic rows are not authenticated evidence."""
import copy
import importlib
import importlib.util
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_ab import MODEL as B_MODEL, candidate as b_candidate
from model_market_challenger import MODEL as C_MODEL, candidate as c_candidate
from research_center import score as canonical_score


def paired_fixture():
    model, market = [.6, .25, .15], [.5, .3, .2]
    return {
        "case_id": "synthetic-case-1", "league": "bundesliga",
        "home": "VfB Stuttgart", "away": "Borussia Mönchengladbach",
        "forecast_event_id": "openligadb:83212", "market_event_id": "market-event-1",
        "source_fixture_identity": {"provider": "OpenLigaDB", "match_id": "83212"},
        "source_fixture_identity_status": "UNAUTHENTICATED",
        "kickoff_utc": "2026-10-23T18:30:00+00:00",
        "prediction_utc": "2026-10-21T02:08:00+00:00",
        "market_snapshot_utc": "2026-10-21T01:37:00+00:00",
        "market_updated_utc": "2026-10-21T01:33:00+00:00",
        "model": model, "market": market,
        "ab": b_candidate(model), "ab_model": B_MODEL,
        "c": c_candidate(model, market), "c_model": C_MODEL,
        "c_uses_only_prior_de_vigged_market": True,
        "c_research_only_not_calibrated_or_executable": True,
        "production_recommendations": "DISABLED", "available_for_betting": False,
        "independently_verified": False, "eligible_for_model_scoring": False,
        "result": None, "historical_outcome": None,
    }


class CaseFourwayScoringTests(unittest.TestCase):
    def function(self):
        self.assertIsNotNone(importlib.util.find_spec("ops.case_fourway_scoring"),
                             "No same-pair four-way candidate scoring boundary exists")
        return importlib.import_module("ops.case_fourway_scoring").score_case

    def assert_held(self, report):
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertIs(report["candidate_only"], True)
        self.assertEqual(report["certified_case_count"], 0)
        self.assertIs(type(report["certified_case_count"]), int)
        for field in ("independently_verified", "eligible_for_model_scoring",
                      "eligible_for_betting_promotion", "results_independently_verified",
                      "model_advantage_vs_market_proven", "market_is_executable_price"):
            self.assertIs(report[field], False, field)

    def test_same_original_pair_scores_all_four_for_each_outcome(self):
        pair = paired_fixture()
        for goals, outcome in (([2, 1], 0), ([1, 1], 1), ([1, 2], 2)):
            with self.subTest(goals=goals):
                report = self.function()(pair, goals)
                self.assert_held(report)
                self.assertEqual(report["y"], outcome)
                self.assertEqual(report["score_ft_candidate"], goals)
                for field in ("case_id", "league", "home", "away",
                              "forecast_event_id", "market_event_id", "prediction_utc",
                              "market_snapshot_utc", "market_updated_utc"):
                    self.assertEqual(report[field], pair[field])
                self.assertEqual(report["recorded_kickoff_utc"], pair["kickoff_utc"])
                self.assertEqual(set(report["models"]), {"A", "B", "C", "market"})
                for name, field in (("A", "model"), ("B", "ab"), ("C", "c"), ("market", "market")):
                    item = report["models"][name]
                    self.assertEqual(item["source_field"], field)
                    self.assertEqual(item["probabilities"], pair[field])
                    expected_loss, expected_brier = canonical_score(pair[field], outcome)
                    self.assertEqual(item["log_loss"], expected_loss)
                    self.assertEqual(item["brier"], expected_brier)
                self.assertEqual(report["models"]["B"]["model_id"], B_MODEL)
                self.assertEqual(report["models"]["C"]["model_id"], C_MODEL)
                self.assertNotIn("model_id", report["models"]["A"])
                self.assertNotIn("model_id", report["models"]["market"])

    def test_zero_probability_retains_canonical_log_loss_clipping(self):
        pair = paired_fixture()
        pair.update(model=[1, 0, 0], market=[0, 1, 0])
        pair.update(ab=b_candidate(pair["model"]), c=c_candidate(pair["model"], pair["market"]))
        report = self.function()(pair, [0, 1])
        for name in ("A", "C", "market"):
            self.assertEqual(report["models"][name]["log_loss"], -math.log(1e-15))
        self.assertEqual(report["models"]["A"]["brier"], 2)
        self.assertEqual(report["models"]["A"]["probabilities"], [1, 0, 0])
        self.assert_held(report)

    def test_input_vectors_and_score_are_never_mutated_or_shared(self):
        pair, goals = paired_fixture(), [2, 3]
        before = copy.deepcopy(pair)
        report = self.function()(pair, goals)
        self.assertEqual(pair, before)
        report["models"]["A"]["probabilities"][0] = 0
        report["score_ft_candidate"][0] = 9
        self.assertEqual(pair, before)
        self.assertEqual(goals, [2, 3])

    def test_accepted_rounding_drift_is_scored_without_renormalizing_sealed_vectors(self):
        pair = paired_fixture()
        pair["model"] = [.6000001, .25, .15]
        pair["market"] = [.5005, .3, .2]
        pair.update(ab=b_candidate(pair["model"]), c=c_candidate(pair["model"], pair["market"]))
        report = self.function()(pair, [2, 3])
        self.assertEqual(report["models"]["market"]["probabilities"], [.5005, .3, .2])
        self.assertEqual(report["models"]["market"]["brier"], canonical_score(pair["market"], 2)[1])

    def test_extreme_datetime_boundaries_return_only_sanitized_value_error(self):
        pair = paired_fixture()
        pair["kickoff_utc"] = "0001-01-01T00:00:00+00:00"
        with self.assertRaisesRegex(ValueError, "^INVALID_PAIRED_CHRONOLOGY$"):
            self.function()(pair, [2, 3])

    def test_invalid_goal_types_bounds_and_shapes_are_rejected(self):
        for goals in (None, "2:3", (2, 3), [], [2], [2, 3, 4], [True, 1],
                      [1, False], [1.0, 2], [-1, 2], [31, 2], [1, 10**400]):
            with self.subTest(goals=repr(goals)):
                with self.assertRaisesRegex(ValueError, "^INVALID_SCORE_FT_CANDIDATE$"):
                    self.function()(paired_fixture(), goals)
        self.assertEqual(self.function()(paired_fixture(), [0, 30])["y"], 2)

    def test_malformed_probability_vectors_fail_before_scoring(self):
        invalid = (None, (), [1], [True, 0, 0], [False, .5, .5],
                   [float("nan"), .5, .5], [float("inf"), 0, 0],
                   [-.1, .5, .6], [.4, .4, .4], [".5", .3, .2], [10**400, 0, 0])
        for field in ("model", "market", "ab", "c"):
            for vector in invalid:
                with self.subTest(field=field, vector=repr(vector)):
                    pair = paired_fixture()
                    pair[field] = vector
                    with self.assertRaises(ValueError):
                        self.function()(pair, [2, 3])

    def test_sealed_candidates_and_registered_ids_cannot_be_reconstructed(self):
        for field, value in (("ab", [.7, .2, .1]), ("c", [.7, .2, .1]),
                             ("ab_model", "later-refitted-B"), ("c_model", "later-refitted-C"),
                             ("c_uses_only_prior_de_vigged_market", False),
                             ("c_research_only_not_calibrated_or_executable", False)):
            with self.subTest(field=field):
                pair = paired_fixture()
                pair[field] = value
                with self.assertRaises(ValueError):
                    self.function()(pair, [2, 3])
        for missing in ("ab", "ab_model", "c", "c_model"):
            with self.subTest(missing=missing):
                pair = paired_fixture()
                pair.pop(missing)
                with self.assertRaises(ValueError):
                    self.function()(pair, [2, 3])

    def test_market_and_prediction_chronology_are_preserved(self):
        for field, value in (
            ("market_updated_utc", "2026-10-21T01:38:00Z"),
            ("market_snapshot_utc", "2026-10-21T02:09:00Z"),
            ("prediction_utc", "2026-10-23T18:21:00Z"),
            ("prediction_utc", "2026-10-23T18:30:00Z"),
            ("prediction_utc", "2026-10-24T00:00:00Z"),
            ("market_updated_utc", "2026-10-20T16:00:00Z"),
            ("market_snapshot_utc", "2026-10-20T12:00:00Z"),
        ):
            with self.subTest(field=field, value=value):
                pair = paired_fixture()
                pair[field] = value
                with self.assertRaisesRegex(ValueError, "^INVALID_PAIRED_CHRONOLOGY$"):
                    self.function()(pair, [2, 3])
        pair = paired_fixture()
        pair.update(prediction_utc="2026-10-23T18:20:00Z",
                    market_snapshot_utc="2026-10-23T18:20:00Z",
                    market_updated_utc="2026-10-23T18:20:00Z")
        self.assert_held(self.function()(pair, [2, 3]))

    def test_missing_naive_or_malformed_times_are_sanitized(self):
        for field in ("kickoff_utc", "prediction_utc", "market_snapshot_utc", "market_updated_utc"):
            for value in (None, "", "2026-10-21T02:08:00", "private-sensitive-invalid-time", 123):
                with self.subTest(field=field, value=value):
                    pair = paired_fixture()
                    pair[field] = value
                    with self.assertRaisesRegex(ValueError, "^INVALID_PAIRED_CHRONOLOGY$"):
                        self.function()(pair, [2, 3])

    def test_identity_fields_and_source_claims_cannot_conflict(self):
        for field in ("case_id", "market_event_id", "forecast_event_id", "league", "home", "away"):
            for value in (None, "", "   ", " padded ", "bad\nidentity", True, []):
                with self.subTest(field=field, value=repr(value)):
                    pair = paired_fixture()
                    pair[field] = value
                    with self.assertRaises(ValueError):
                        self.function()(pair, [2, 3])
        pair = paired_fixture()
        pair["source_fixture_identity"]["match_id"] = "999"
        with self.assertRaisesRegex(ValueError, "^INVALID_PAIRED_IDENTITY$"):
            self.function()(pair, [2, 3])
        pair = paired_fixture()
        pair["away"] = pair["home"]
        with self.assertRaises(ValueError):
            self.function()(pair, [2, 3])

    def test_prepopulated_outcomes_and_promotion_claims_are_rejected(self):
        changes = {
            "production_recommendations": "ENABLED", "available_for_betting": True,
            "independently_verified": True, "eligible_for_model_scoring": True,
            "eligible_for_betting_promotion": True, "results_independently_verified": True,
            "result_verified": True, "outcomes_independently_authenticated": True,
            "ready_for_production": True, "automatic_bets": True,
            "certified_case_count": 1, "result": "away", "historical_outcome": 2,
            "score_ft": [2, 3], "y": 2,
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                pair = paired_fixture()
                pair[field] = value
                with self.assertRaisesRegex(ValueError, "^UNSAFE_OR_RESULT_BEARING_PAIR$"):
                    self.function()(pair, [2, 3])
        for field in ("independently_verified", "eligible_for_model_scoring", "available_for_betting"):
            for value in (0, None, "false"):
                with self.subTest(field=field, value=value):
                    pair = paired_fixture()
                    pair[field] = value
                    with self.assertRaises(ValueError):
                        self.function()(pair, [2, 3])

    def test_non_object_pair_is_sanitized(self):
        for pair in (None, [], "private-sensitive-pair", False):
            with self.subTest(pair=repr(pair)):
                with self.assertRaisesRegex(ValueError, "^INVALID_PAIRED_CASE$"):
                    self.function()(pair, [2, 3])


if __name__ == "__main__":
    unittest.main()
