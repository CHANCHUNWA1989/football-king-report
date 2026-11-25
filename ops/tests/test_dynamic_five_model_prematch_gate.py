"""A + Poisson + Dixon-Coles + Bivariate + Dynamic pre-kickoff shadow."""
from copy import deepcopy
from datetime import datetime, timedelta
import unittest

from ops.dynamic_five_model_prematch_gate import attach
from ops.bivariate_four_model_prematch_gate import attach as attach_four
from ops.tests.test_bivariate_four_model_prematch_gate import cohort, fake_clock
from ops.tests.test_penaltyblog_bivariate_goals_challenger import FakeModel


def ready():
    payload, triple = cohort()
    cutoff = datetime.fromisoformat(payload["decision_cutoff_utc"])
    four = attach_four(
        payload, triple, same_a_training_rows=True,
        clock=fake_clock(cutoff-timedelta(seconds=40),
                         cutoff-timedelta(seconds=25)), model_factory=FakeModel)
    assert four["reason"] == "LOCAL_FOUR_MODEL_PREMATCH_CAPTURE_UNATTESTED", four
    return payload, four, cutoff


class FiveModelPrematchTests(unittest.TestCase):
    def test_full_five_families_on_same_identity_before_cutoff(self):
        payload, four, cutoff = ready()
        before = deepcopy((payload, four))
        result = attach(payload, four, clock=fake_clock(
            cutoff-timedelta(seconds=15),
            cutoff-timedelta(seconds=5)))
        self.assertEqual((payload, four), before)
        self.assertEqual(result["reason"],
                         "LOCAL_FIVE_MODEL_PREMATCH_RESEARCH_UNATTESTED")
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["history_source_match_count"], 40)
        for model in ("original_a_1x2", "poisson_1x2", "dixon_coles_1x2",
                      "bivariate_poisson_1x2", "dynamic_score_poisson_1x2"):
            self.assertAlmostEqual(sum(result[model]), 1, places=8)
        self.assertEqual(result["original_a_1x2"], four["original_a_1x2"])
        self.assertEqual(result["bivariate_poisson_1x2"],
                         four["bivariate_poisson_1x2"])
        self.assertGreater(result["dynamic_expected_home_goals"], 0)
        self.assertAlmostEqual(sum(result["dynamic_over_2_75_settlement"].values()), 1)
        self.assertAlmostEqual(sum(
            result["dynamic_home_ah_minus_0_25_settlement"].values()), 1)
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertEqual(result["certified_prospective_samples"], 0)
        self.assertFalse(result["positive_ev_verified"])
        self.assertFalse(result["all_five_eligible_for_betting"])
        self.assertFalse(result["independently_timestamped"])

    def test_after_cutoff_never_reclassifies_past_fixture(self):
        payload, four, cutoff = ready()
        for moment in (cutoff, cutoff + timedelta(hours=4)):
            result = attach(payload, four, clock=fake_clock(moment))
            self.assertEqual(result["reason"],
                             "FIFTH_MODEL_NOT_PREMATCH_OR_AFTER_CUTOFF")
            self.assertNotIn("dynamic_score_poisson_1x2", result)

    def test_executing_during_cutoff_returns_no_partial_probabilities(self):
        payload, four, cutoff = ready()
        result = attach(payload, four, clock=fake_clock(
            cutoff-timedelta(seconds=10), cutoff+timedelta(seconds=1)))
        self.assertEqual(result["reason"], "FIFTH_MODEL_CROSSED_PREMATCH_CUTOFF")
        self.assertNotIn("dynamic_score_poisson_1x2", result)

    def test_tampered_prior_model_or_team_ids_are_rejected(self):
        for tamper in ("wrong_team", "bad_probability", "missing_history",
                       "promoted", "source_id"):
            payload, four, cutoff = ready()
            if tamper == "wrong_team":
                payload["original_a"]["away_team_id"] = "different"
            elif tamper == "bad_probability":
                four["dixon_coles_1x2"] = [float("nan"), 0.5, 0.5]
            elif tamper == "missing_history":
                four["training_match_count"] = 39
            elif tamper == "promoted":
                four["model_promoted"] = True
            else:
                four["source_namespace"] = "other"
            with self.subTest(tamper=tamper):
                result = attach(payload, four, clock=fake_clock(
                    cutoff-timedelta(seconds=15),
                    cutoff-timedelta(seconds=5)))
                self.assertNotEqual(result["reason"],
                                    "LOCAL_FIVE_MODEL_PREMATCH_RESEARCH_UNATTESTED")
                self.assertNotIn("dynamic_score_poisson_1x2", result)

    def test_known_after_cutoff_result_is_rejected(self):
        payload, four, cutoff = ready()
        payload["historical_matches"][-1]["result_recorded_utc"] = (
            cutoff + timedelta(seconds=1)).isoformat()
        result = attach(payload, four, clock=fake_clock(
            cutoff-timedelta(seconds=15),
            cutoff-timedelta(seconds=5)))
        self.assertEqual(result["reason"], "DYNAMIC_FIT_OR_TIME_OR_SOURCE_MISMATCH")
        self.assertNotIn("dynamic_score_poisson_1x2", result)


if __name__ == "__main__":
    unittest.main()
