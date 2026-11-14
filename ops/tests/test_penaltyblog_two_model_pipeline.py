import copy
import unittest
from ops.penaltyblog_two_model_pipeline import run_pipeline
from ops.tests.test_penaltyblog_walkforward_refit import cohort, FakeModel


def fixture():
    data = cohort()
    results = []
    for index, target in enumerate(data["targets"]):
        results.append({
            "fixture_id": target["event_id"],
            "kickoff_utc": target["kickoff_utc"],
            "outcome": ("H", "D")[index],
            "result_recorded_utc": target["kickoff_utc"][:10] + "T23:00:00+00:00",
        })
    return {
        "schema": "football-king-two-model-pipeline-v1",
        "production_recommendations": "DISABLED",
        "historical_matches": data["historical_matches"],
        "targets": data["targets"],
        "results": results,
        "min_training": 30,
    }


FACTORIES = {"poisson": FakeModel, "dixon_coles": FakeModel}


class PipelineTests(unittest.TestCase):
    def setUp(self):
        FakeModel.calls = []

    def test_two_model_end_to_end_diagnostics(self):
        r = run_pipeline(fixture(), model_factories=FACTORIES)
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["paired_fixture_count"], 2)
        self.assertEqual(r["model_refit_counts"], {"poisson": 2, "dixon_coles": 2})
        self.assertEqual(len(FakeModel.calls), 4)
        self.assertEqual(r["unverified_diagnostic_metrics"]["poisson"]["sample_count"], 2)
        self.assertFalse(r["positive_ev_verified"])

    def test_missing_result_blocks_before_fit(self):
        data = fixture()
        data["results"].pop()
        r = run_pipeline(data, model_factories=FACTORIES)
        self.assertEqual(r["reason"], "TARGET_RESULT_COHORT_MISMATCH")
        self.assertEqual(FakeModel.calls, [])

    def test_duplicate_target_blocks(self):
        data = fixture()
        data["targets"].append(copy.deepcopy(data["targets"][-1]))
        self.assertEqual(run_pipeline(data, model_factories=FACTORIES)["reason"],
                         "DUPLICATE_TARGET")

    def test_duplicate_result_blocks(self):
        data = fixture()
        data["results"].append(copy.deepcopy(data["results"][0]))
        self.assertEqual(run_pipeline(data, model_factories=FACTORIES)["reason"],
                         "DUPLICATE_RESULT")

    def test_missing_training_blocks_without_partial_scores(self):
        data = fixture()
        data["min_training"] = 49
        r = run_pipeline(data, model_factories=FACTORIES)
        self.assertEqual(r["reason"], "MODEL_REFIT_BLOCKED")
        self.assertNotIn("unverified_diagnostic_metrics", r)

    def test_invalid_production_flag_blocks(self):
        data = fixture()
        data["production_recommendations"] = "ENABLED"
        self.assertEqual(run_pipeline(data, model_factories=FACTORIES)["reason"],
                         "INVALID_CONTRACT")

    def test_model_fit_failure_blocks(self):
        class BadModel(FakeModel):
            def fit(self):
                raise RuntimeError("bad fit")
        r = run_pipeline(fixture(), model_factories={"poisson": FakeModel, "dixon_coles": BadModel})
        self.assertEqual(r["reason"], "MODEL_REFIT_BLOCKED")
        self.assertEqual(r["blocked_model"], "dixon_coles")
        self.assertNotIn("unverified_diagnostic_metrics", r)


if __name__ == "__main__":
    unittest.main()
