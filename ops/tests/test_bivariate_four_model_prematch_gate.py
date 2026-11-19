"""Four-model pre-kickoff contract tests; no sports result/odds fabrication."""
import copy
from datetime import datetime, timedelta
import unittest

from ops.bivariate_four_model_prematch_gate import attach
from ops.tests.test_penaltyblog_bivariate_goals_challenger import FakeModel
from ops.tests.test_penaltyblog_time_decay_research import fixture


def cohort():
    original = fixture()
    cutoff = datetime.fromisoformat(original["as_of_utc"])
    target = original["target_fixture"]
    initial = {
        "schema": "football-king-prekickoff-a-penaltyblog-dual-handoff-v1",
        "production_recommendations": "DISABLED",
        "decision_cutoff_utc": cutoff.isoformat(),
        "original_a": {
            **target, "model_id": "poisson-shrinkage-unvalidated-v4.1",
            "probabilities": [0.5, 0.3, 0.2],
            "source_authenticity_verified": False,
            "independently_timestamped": False,
            "production_recommendations": "DISABLED",
        },
        "historical_matches": original["historical_matches"],
    }
    obs = [
        {"model": "poisson", "training_match_count": 40,
         "probabilities": [0.45, 0.30, 0.25]},
        {"model": "dixon_coles", "training_match_count": 40,
         "probabilities": [0.43, 0.32, 0.25]},
    ]
    body = {
        "event_id": target["event_id"],
        "source_namespace": target["source_namespace"],
        "league_id": target["league_id"],
        "home_team_id": target["home_team_id"],
        "away_team_id": target["away_team_id"],
        "kickoff_utc": target["kickoff_utc"],
        "decision_cutoff_utc": cutoff.isoformat(),
        "last_local_capture_observed_utc":
            (cutoff - timedelta(minutes=1)).isoformat(),
        "original_a_probabilities": [0.5, 0.3, 0.2],
        "challenger_observations": obs,
    }
    return initial, {
        "status": "HOLD",
        "reason": "LOCAL_A_POISSON_DC_CAPTURE_NOT_EXTERNALLY_ATTESTED",
        "production_recommendations": "DISABLED",
        "positive_ev_verified": False,
        "certified_prospective_samples": 0,
        "unverified_triple_capture": body,
    }


def fake_clock(*values):
    iterator = iter(values)
    return lambda: next(iterator)


class FourModelPrematchTests(unittest.TestCase):
    def setUp(self):
        FakeModel.calls = []

    def test_four_real_algorithm_outputs_remain_unverified_and_pre_cutoff(self):
        p, triple = cohort()
        before = copy.deepcopy((p, triple))
        cutoff = datetime.fromisoformat(p["decision_cutoff_utc"])
        result = attach(
            p, triple, same_a_training_rows=True,
            clock=fake_clock(cutoff-timedelta(seconds=30),
                             cutoff-timedelta(seconds=10)),
            model_factory=FakeModel)
        self.assertEqual((p, triple), before)
        self.assertEqual(result["reason"],
                         "LOCAL_FOUR_MODEL_PREMATCH_CAPTURE_UNATTESTED")
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["training_match_count"], 40)
        self.assertEqual(result["original_a_1x2"], [0.5, 0.3, 0.2])
        self.assertEqual(result["poisson_1x2"], [0.45, 0.3, 0.25])
        self.assertEqual(result["dixon_coles_1x2"], [0.43, 0.32, 0.25])
        self.assertEqual(result["bivariate_poisson_1x2"], [0.6, 0.2, 0.2])
        self.assertEqual(result["bivariate_poisson_time_decay_1x2"],
                         [0.5, 0.3, 0.2])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertEqual(result["certified_prospective_samples"], 0)
        self.assertFalse(result["positive_ev_verified"])
        self.assertFalse(result["bookmaker_quotes_verified"])
        self.assertEqual(len(FakeModel.calls), 2)

    def test_missing_identical_history_blocks_fitting(self):
        p, triple = cohort()
        result = attach(p, triple, same_a_training_rows=False,
                        clock=lambda: (_ for _ in ()).throw(AssertionError()),
                        model_factory=FakeModel)
        self.assertEqual(result["reason"], "A_AND_CHALLENGERS_HISTORY_NOT_IDENTICAL")
        self.assertEqual(FakeModel.calls, [])

    def test_after_kickoff_or_cutoff_not_a_forecast(self):
        p, triple = cohort()
        cutoff = datetime.fromisoformat(p["decision_cutoff_utc"])
        for when in (cutoff, cutoff + timedelta(hours=2)):
            with self.subTest(when=when):
                output = attach(p, triple, same_a_training_rows=True,
                                clock=fake_clock(when), model_factory=FakeModel)
                self.assertEqual(output["reason"],
                                 "FOURTH_MODEL_NOT_PREMATCH_OR_AFTER_CUTOFF")
        self.assertEqual(FakeModel.calls, [])

    def test_execution_crosses_cutoff_never_outputs_partial_probs(self):
        p, triple = cohort()
        cutoff = datetime.fromisoformat(p["decision_cutoff_utc"])
        result = attach(
            p, triple, same_a_training_rows=True,
            clock=fake_clock(cutoff-timedelta(seconds=30),
                             cutoff+timedelta(seconds=1)),
            model_factory=FakeModel)
        self.assertEqual(result["reason"], "FOURTH_MODEL_EXECUTION_CROSSED_CUTOFF")
        self.assertNotIn("bivariate_poisson_1x2", result)
        self.assertEqual(len(FakeModel.calls), 2)

    def test_mismatched_native_id_or_history_count_rejected(self):
        for change in ("native", "count", "third"):
            p, triple = cohort()
            if change == "native":
                triple["unverified_triple_capture"]["home_team_id"] = "other"
            if change == "count":
                triple["unverified_triple_capture"]["challenger_observations"][0][
                    "training_match_count"] = 39
            if change == "third":
                triple["unverified_triple_capture"]["challenger_observations"].append({
                    "model": "fake", "training_match_count": 40,
                    "probabilities": [0.4, 0.3, 0.3],
                })
            with self.subTest(change=change):
                output = attach(p, triple, same_a_training_rows=True,
                                clock=lambda: (_ for _ in ()).throw(AssertionError()),
                                model_factory=FakeModel)
                self.assertNotIn("bivariate_poisson_1x2", output)
        self.assertEqual(FakeModel.calls, [])

    def test_history_future_result_rejected_without_partial_output(self):
        p, triple = cohort()
        p["historical_matches"][-1]["result_recorded_utc"] = p["decision_cutoff_utc"]
        cutoff = datetime.fromisoformat(p["decision_cutoff_utc"])
        out = attach(p, triple, same_a_training_rows=True,
                     clock=fake_clock(cutoff-timedelta(seconds=30),
                                      cutoff-timedelta(seconds=10)),
                     model_factory=FakeModel)
        self.assertEqual(out["reason"], "FOURTH_MODEL_FIT_OR_SOURCE_MISMATCH")
        self.assertNotIn("bivariate_poisson_1x2", out)
        self.assertEqual(FakeModel.calls, [])


if __name__ == "__main__":
    unittest.main()
