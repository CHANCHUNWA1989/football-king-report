import copy
import math
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from ops.penaltyblog_paired_uncertainty import assess
from ops.tests.test_penaltyblog_paired_refit_score import sample


def many(n=36):
    data = sample()
    data["results"] = []
    for model in ("poisson", "dixon_coles"):
        data["model_runs"][model]["predictions"] = []
        data["model_runs"][model]["refit_count"] = n
    for i in range(n):
        day = (i % 27) + 1
        month = 11 + i // 27
        kickoff = f"2026-{month:02d}-{day:02d}T20:00:00Z"
        asof = f"2026-{month:02d}-{day:02d}T18:00:00Z"
        data["results"].append({"fixture_id": f"f{i}", "kickoff_utc": kickoff,
                                "result_recorded_utc": f"2026-{month:02d}-{day:02d}T23:00:00Z",
                                "outcome": ("H", "D", "A")[i % 3]})
        for model in ("poisson", "dixon_coles"):
            data["model_runs"][model]["predictions"].append({
                "fixture_id": f"f{i}", "kickoff_utc": kickoff,
                "as_of_utc": asof,
                "model_id": f"penaltyblog-{model}-offline-challenger-v1",
                "training_match_count": 40 + i,
                "probabilities": [.5, .3, .2] if model == "poisson" else [.4, .35, .25],
                "source_authenticity_verified": False, "independently_timestamped": False})
    return data


def weekly_cohort(sizes):
    data = sample()
    data["results"] = []
    for model in ("poisson", "dixon_coles"):
        data["model_runs"][model]["predictions"] = []
        data["model_runs"][model]["refit_count"] = sum(sizes)
    for week, size in enumerate(sizes):
        kickoff = datetime(2026, 1, 5, 20, tzinfo=timezone.utc) + timedelta(weeks=week)
        for index in range(size):
            fixture_id = f"week-{week}-fixture-{index}"
            data["results"].append({
                "fixture_id": fixture_id, "kickoff_utc": kickoff.isoformat(),
                "result_recorded_utc": (kickoff + timedelta(hours=3)).isoformat(), "outcome": "H"})
            for model in ("poisson", "dixon_coles"):
                wins = (model == "dixon_coles") == (week % 2 == 0)
                data["model_runs"][model]["predictions"].append({
                    "fixture_id": fixture_id, "kickoff_utc": kickoff.isoformat(),
                    "as_of_utc": (kickoff - timedelta(hours=2)).isoformat(),
                    "model_id": f"penaltyblog-{model}-offline-challenger-v1",
                    "training_match_count": 40,
                    "probabilities": [.5, .25, .25] if wins else [.25, .25, .5],
                    "source_authenticity_verified": False, "independently_timestamped": False})
    return data


class UncertaintyTests(unittest.TestCase):
    def test_small_sample_refuses_confidence_interval(self):
        r = assess(sample())
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["sample_count"], 2)
        self.assertIsNone(r["paired_iid_bootstrap_95pct_intervals"])
        self.assertEqual(r["interval_status"], "INSUFFICIENT_SAMPLE_N_LT_30")

    def test_paired_bootstrap_deterministic(self):
        data = many()
        a = assess(data, bootstrap_repeats=200, seed=17)
        b = assess(data, bootstrap_repeats=200, seed=17)
        self.assertEqual(a, b)
        self.assertEqual(a["sample_count"], 36)
        self.assertEqual(a["interval_status"], "COMPUTED_IID_RESEARCH_ONLY")
        self.assertEqual(set(a["paired_iid_bootstrap_95pct_intervals"]),
                         {"accuracy", "brier", "log_loss"})
        self.assertFalse(a["model_promoted"])

    def test_equivalent_kickoff_offsets_preserve_bootstrap_and_input(self):
        data = many()
        expected = assess(data, bootstrap_repeats=200, seed=17)
        for row in data["results"]:
            instant = datetime.fromisoformat(row["kickoff_utc"].replace("Z", "+00:00"))
            row["kickoff_utc"] = instant.astimezone(timezone(timedelta(hours=-5))).isoformat()
        for model in ("poisson", "dixon_coles"):
            for row in data["model_runs"][model]["predictions"]:
                instant = datetime.fromisoformat(row["kickoff_utc"].replace("Z", "+00:00"))
                row["kickoff_utc"] = instant.astimezone(timezone(timedelta(hours=8))).isoformat()
        original = copy.deepcopy(data)
        self.assertEqual(assess(data, bootstrap_repeats=200, seed=17), expected)
        self.assertEqual(data, original)

    def test_different_or_naive_kickoff_rejects_all_metrics_and_intervals(self):
        for model in ("poisson", "dixon_coles"):
            for value in ("2026-11-08T20:00:01Z", "2026-11-08T19:59:59Z",
                          "2026-11-08T20:00:00"):
                with self.subTest(model=model, value=value):
                    data = sample()
                    data["model_runs"][model]["predictions"][0]["kickoff_utc"] = value
                    report = assess(data)
                    self.assertEqual(report["status"], "HOLD")
                    for key in ("sample_count", "unverified_diagnostic_metrics",
                                "paired_delta_dixon_coles_vs_poisson",
                                "paired_iid_bootstrap_95pct_intervals"):
                        self.assertNotIn(key, report)
                    self.assertFalse(report["positive_ev_verified"])
                    self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_missing_prediction_fails_entire_cohort(self):
        data = many()
        data["model_runs"]["poisson"]["predictions"].pop()
        r = assess(data)
        self.assertEqual(r["status"], "HOLD")
        self.assertNotIn("paired_delta_dixon_coles_vs_poisson", r)

    def test_cutoff_mismatch_fails_closed(self):
        data = many()
        data["model_runs"]["dixon_coles"]["predictions"][0]["as_of_utc"] = "2026-11-01T17:00:00Z"
        self.assertEqual(assess(data)["reason"], "MODEL_CUTOFF_MISMATCH")

    def test_self_certification_fails_closed(self):
        data = many()
        data["model_runs"]["poisson"]["predictions"][0]["independently_timestamped"] = True
        self.assertEqual(assess(data)["reason"], "UNTRUSTED_PREDICTION")

    def test_invalid_probability_fails_closed(self):
        data = many()
        data["model_runs"]["poisson"]["predictions"][0]["probabilities"] = [.9, .9, -.8]
        self.assertEqual(assess(data)["reason"], "INVALID_PROBABILITIES")

    def test_duplicate_result_fails_closed(self):
        data = many()
        data["results"][1]["fixture_id"] = data["results"][0]["fixture_id"]
        self.assertEqual(assess(data)["reason"], "DUPLICATE_OR_INVALID_FIXTURE")

    def test_invalid_bootstrap_settings_fail_closed(self):
        self.assertEqual(assess(many(), bootstrap_repeats=10)["reason"],
                         "INVALID_BOOTSTRAP_SETTINGS")

    def test_weekly_intervals_require_both_fixture_and_week_floors(self):
        cases = (([2] * 12, "INSUFFICIENT_SAMPLE_N_LT_30"),
                 ([3] * 11, "INSUFFICIENT_UTC_WEEK_BLOCKS_LT_12"))
        for sizes, reason in cases:
            with self.subTest(sizes=sizes):
                report = assess(weekly_cohort(sizes), bootstrap_repeats=200)
                self.assertIn("week_block_count", report)
                self.assertEqual(report["week_block_count"], len(sizes))
                self.assertEqual(report["week_block_interval_status"], reason)
                self.assertIsNone(report["paired_week_block_bootstrap_95pct_intervals"])
                self.assertEqual(report["week_block_bootstrap_repeats"], 0)
        data = weekly_cohort([30])
        report = assess(data, bootstrap_repeats=200)
        self.assertIn("week_block_count", report)
        self.assertEqual(report["interval_status"], "COMPUTED_IID_RESEARCH_ONLY")
        self.assertEqual(report["week_block_count"], 1)
        self.assertIsNone(report["paired_week_block_bootstrap_95pct_intervals"])

    def test_exact_weekly_floors_enable_only_research_intervals(self):
        data = weekly_cohort([3] * 6 + [2] * 6)
        original = copy.deepcopy(data)
        report = assess(data, bootstrap_repeats=200, seed=17)
        self.assertIn("week_block_count", report)
        self.assertEqual(report["sample_count"], 30)
        self.assertEqual(report["week_block_count"], 12)
        self.assertEqual(report["week_block_interval_status"], "COMPUTED_WEEK_BLOCK_RESEARCH_ONLY")
        self.assertEqual(report["week_block_bootstrap_repeats"], 200)
        self.assertEqual(set(report["paired_week_block_bootstrap_95pct_intervals"]),
                         {"accuracy", "brier", "log_loss"})
        self.assertEqual(report["status"], "HOLD")
        self.assertFalse(report["positive_ev_verified"])
        self.assertFalse(report["model_promoted"])
        self.assertEqual(data, original)

    def test_correlated_weeks_keep_joint_pairs_and_differ_from_iid(self):
        # Within each synthetic week all differences share the same sign.
        data = weekly_cohort([3] * 12)
        original = copy.deepcopy(data)
        report = assess(data, bootstrap_repeats=1000, seed=17)
        self.assertIn("paired_week_block_bootstrap_95pct_intervals", report)
        bounds = report["paired_week_block_bootstrap_95pct_intervals"]
        iid = report["paired_iid_bootstrap_95pct_intervals"]
        self.assertGreater(bounds["accuracy"][1] - bounds["accuracy"][0],
                           iid["accuracy"][1] - iid["accuracy"][0])
        for index in (0, 1):
            self.assertAlmostEqual(bounds["brier"][index], .5 * bounds["accuracy"][index])
            self.assertAlmostEqual(bounds["log_loss"][index], math.log(2) * bounds["accuracy"][index])
        data["results"].reverse()
        for model in data["model_runs"].values():
            model["predictions"].reverse()
        self.assertEqual(assess(data, bootstrap_repeats=1000, seed=17), report)
        self.assertEqual(assess(original, bootstrap_repeats=1000, seed=17), report)

    def test_weekly_draws_weight_fixtures_instead_of_averaging_week_means(self):
        class Cycle:
            def __init__(self, seed):
                self.index = 0
            def randrange(self, size):
                value = self.index % size
                self.index += 1
                return value
        # Every deterministic draw selects each week once. 20 wins, 12 losses:
        # accuracy delta = 8/32=.25, while an unweighted week mean would be 0.
        data = weekly_cohort([10] + [2] * 11)
        with patch("ops.penaltyblog_paired_uncertainty.random.Random", Cycle):
            report = assess(data, bootstrap_repeats=200)
        self.assertIn("paired_week_block_bootstrap_95pct_intervals", report)
        bounds = report["paired_week_block_bootstrap_95pct_intervals"]
        self.assertEqual(bounds["accuracy"], [.25, .25])
        self.assertEqual(bounds["brier"], [.125, .125])
        for value in bounds["log_loss"]:
            self.assertAlmostEqual(value, .25 * math.log(2))
        class RepeatFirst(Cycle):
            def randrange(self, size):
                return 0
        # Twelve copies of the 10-fixture first week contain 120 wins, so
        # divide by 120 sampled fixtures, not the 32 original fixtures.
        with patch("ops.penaltyblog_paired_uncertainty.random.Random", RepeatFirst):
            repeated = assess(data, bootstrap_repeats=200)
        bounds = repeated["paired_week_block_bootstrap_95pct_intervals"]
        self.assertEqual(bounds["accuracy"], [1.0, 1.0])
        self.assertEqual(bounds["brier"], [.5, .5])
        for value in bounds["log_loss"]:
            self.assertAlmostEqual(value, math.log(2))

    def test_week_groups_use_utc_iso_year_at_boundaries(self):
        data = weekly_cohort([12, 12, 12])
        times = ("2020-12-28T20:00:00+00:00", "2021-01-03T23:30:00+00:00",
                 "2021-01-04T00:30:00+00:00")
        for index, result in enumerate(data["results"]):
            instant = datetime.fromisoformat(times[index // 12])
            result["kickoff_utc"] = instant.astimezone(timezone(timedelta(hours=8))).isoformat()
            result["result_recorded_utc"] = (instant + timedelta(hours=3)).isoformat()
            for model in data["model_runs"].values():
                row = model["predictions"][index]
                row["kickoff_utc"] = instant.isoformat()
                row["as_of_utc"] = (instant - timedelta(hours=2)).isoformat()
        report = assess(data, bootstrap_repeats=200)
        self.assertIn("week_block_count", report)
        self.assertEqual(report["week_block_count"], 2)
        self.assertIsNone(report["paired_week_block_bootstrap_95pct_intervals"])

    def test_invalid_cohort_never_exposes_partial_weekly_counts_or_intervals(self):
        data = weekly_cohort([3] * 12)
        data["model_runs"]["dixon_coles"]["predictions"][-1]["as_of_utc"] = "2099-01-01T00:00:00Z"
        report = assess(data, bootstrap_repeats=200)
        for key in ("week_block_count", "paired_week_block_bootstrap_95pct_intervals",
                    "week_block_bootstrap_repeats"):
            self.assertNotIn(key, report)
        self.assertEqual(report["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
