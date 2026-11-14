import copy
import unittest

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


if __name__ == "__main__":
    unittest.main()
