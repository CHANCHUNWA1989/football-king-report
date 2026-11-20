import copy
import math
import unittest

from ops.league_goal_blend_shadow import audit, MIX_WEIGHT

REV = "e6744429ee395bc86f247348c6184bb08d4eb361"


def fixture(label, i, date, home=0, away=0, rate_home=None, rate_away=None):
    row = {"league": "epl", "fixture_id": f"{label}:{i}",
           "match_date": date, "home_goals": home, "away_goals": away}
    if rate_home is not None:
        row["expected_home_goals"] = rate_home
    if rate_away is not None:
        row["expected_away_goals"] = rate_away
    return row


def sample():
    return [{
        "league": "epl",
        "test_season": "2025-26",
        "training": [fixture("train", i, "2025-05-01", home=i % 3,
                             away=0 if i % 2 else 1) for i in range(40)],
        "heldout": [fixture("test", i, "2026-05-01", home=1 if i % 2 else 2,
                            away=i % 2, rate_home=1.4, rate_away=0.9)
                    for i in range(30)],
    }]


class LeagueGoalBlendShadowTests(unittest.TestCase):
    def test_correct_research_scoring_and_hard_veto(self):
        result = audit(sample(), source_revision=REV)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["fixed_training_prior_blend_weight"], MIX_WEIGHT)
        self.assertEqual(result["pooled"]["OVER25"]["sample_count"], 30)
        self.assertFalse(result["eligible_for_model_promotion"])
        self.assertFalse(result["model_profitability_or_positive_ev_verified"])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["source_identity_and_timestamps_independently_authenticated"])
        self.assertIn("BTTS", result["pooled"])
        self.assertEqual(result["folds"][0]["training_samples"], 40)

    def test_fixed_weight_prior_is_training_only(self):
        data = sample()
        first = audit(data, source_revision=REV)
        data[0]["heldout"] = [
            {**r, "home_goals": 7, "away_goals": 4}
            for r in data[0]["heldout"]]
        second = audit(data, source_revision=REV)
        self.assertEqual(first["folds"][0]["prior_over25_from_training_only"],
                         second["folds"][0]["prior_over25_from_training_only"])
        self.assertEqual(first["folds"][0]["prior_btts_from_training_only"],
                         second["folds"][0]["prior_btts_from_training_only"])
        self.assertNotEqual(first["pooled"]["OVER25"]["observed_rate"],
                            second["pooled"]["OVER25"]["observed_rate"])
        self.assertEqual(first["pooled"]["OVER25"]["mean_blend_probability"],
                         second["pooled"]["OVER25"]["mean_blend_probability"])

    def test_poisson_over25_correct(self):
        data = sample()
        data[0]["training"] = [
            {**r, "home_goals": 0, "away_goals": 0}
            for r in data[0]["training"]]
        report = audit(data, source_revision=REV)
        p = 1 - math.exp(-2.3) * (1 + 2.3 + 2.3**2/2)
        expected_prior = 0.5 / 41
        expected_blend = (1-MIX_WEIGHT)*p+MIX_WEIGHT*expected_prior
        self.assertAlmostEqual(report["pooled"]["OVER25"]["mean_model_probability"], p, places=7)
        self.assertAlmostEqual(report["pooled"]["OVER25"]["mean_blend_probability"], expected_blend, places=7)

    def test_reject_train_on_or_after_test_date(self):
        data = sample()
        data[0]["training"][-1]["match_date"] = "2026-05-01"
        with self.assertRaisesRegex(ValueError, "TRAINING_DATA_OVERLAPS_TEST"):
            audit(data, source_revision=REV)

    def test_reject_overlap_or_duplicate_fixture_ids(self):
        data = sample()
        data[0]["heldout"][0]["fixture_id"] = data[0]["training"][0]["fixture_id"]
        with self.assertRaisesRegex(ValueError, "TRAINING_TEST_IDENTITY_OVERLAP"):
            audit(data, source_revision=REV)
        data = sample()
        data[0]["training"][1]["fixture_id"] = data[0]["training"][0]["fixture_id"]
        with self.assertRaisesRegex(ValueError, "DUPLICATE_FIXTURE"):
            audit(data, source_revision=REV)
        data = sample()
        data[0]["heldout"][0]["fixture_id"] = data[0]["heldout"][1]["fixture_id"]
        with self.assertRaisesRegex(ValueError, "DUPLICATE_FIXTURE"):
            audit(data, source_revision=REV)

    def test_reject_false_scores_and_nan_rates(self):
        data = sample()
        data[0]["training"][0]["home_goals"] = True
        with self.assertRaisesRegex(ValueError, "INVALID_FULLTIME_SCORE"):
            audit(data, source_revision=REV)
        data = sample()
        data[0]["heldout"][0]["expected_home_goals"] = float("nan")
        with self.assertRaisesRegex(ValueError, "INVALID_ORIGINAL_GOAL_RATES"):
            audit(data, source_revision=REV)
        data = sample()
        data[0]["heldout"][0]["expected_away_goals"] = True
        with self.assertRaisesRegex(ValueError, "INVALID_ORIGINAL_GOAL_RATES"):
            audit(data, source_revision=REV)

    def test_reject_invalid_source_and_league_conflict(self):
        data = sample()
        with self.assertRaisesRegex(ValueError, "INVALID_PINNED_SOURCE_REVISION"):
            audit(data, source_revision="main")
        data[0]["training"][0]["league"] = "bundesliga"
        with self.assertRaisesRegex(ValueError, "LEAGUE_IDENTITY_MISMATCH"):
            audit(data, source_revision=REV)

    def test_reject_insufficient_fold_and_duplicate_cohort(self):
        data = sample()
        data[0]["training"] = data[0]["training"][:29]
        with self.assertRaisesRegex(ValueError, "INSUFFICIENT_FOLD_SIZE"):
            audit(data, source_revision=REV)
        data = sample()
        data[0]["heldout"] = data[0]["heldout"][:19]
        with self.assertRaisesRegex(ValueError, "INSUFFICIENT_FOLD_SIZE"):
            audit(data, source_revision=REV)
        data = sample()
        with self.assertRaisesRegex(ValueError, "DUPLICATE_LEAGUE_SEASON"):
            audit([data[0], copy.deepcopy(data[0])], source_revision=REV)

    def test_reject_identity_reuse_across_seasons(self):
        data = sample()
        later = copy.deepcopy(data[0])
        later["test_season"] = "2026-27"
        later["training"] = [fixture("newtrain", i, "2026-04-01")
                             for i in range(40)]
        # unique test season but an overlapping fixture ID still fails.
        later["heldout"] = [fixture("test", i, "2027-05-01", rate_home=1.2,
                                    rate_away=0.8) for i in range(30)]
        with self.assertRaisesRegex(ValueError, "DUPLICATE_HELDOUT_ACROSS_FOLDS"):
            audit([data[0], later], source_revision=REV)

    def test_no_input_mutation(self):
        data = sample()
        old = copy.deepcopy(data)
        audit(data, source_revision=REV)
        self.assertEqual(data, old)


if __name__ == "__main__":
    unittest.main()
