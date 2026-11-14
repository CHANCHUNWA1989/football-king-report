import copy
import unittest
from datetime import datetime, timedelta, timezone
from ops.penaltyblog_paired_refit_score import score_paired


def sample():
    kickoffs = ["2026-11-08T20:00:00Z", "2026-11-09T20:00:00Z"]
    results = [{"fixture_id": f"synthetic-{i}", "kickoff_utc": kickoff,
                "result_recorded_utc": f"2026-11-{i + 8:02d}T23:00:00Z",
                "outcome": ("H", "A")[i]} for i, kickoff in enumerate(kickoffs)]
    runs = {}
    for model in ("poisson", "dixon_coles"):
        predictions = []
        for i, kickoff in enumerate(kickoffs):
            predictions.append({
                "fixture_id": f"synthetic-{i}", "kickoff_utc": kickoff,
                "as_of_utc": f"2026-11-{i + 8:02d}T18:00:00Z",
                "model_id": f"penaltyblog-{model}-offline-challenger-v1",
                "training_match_count": 40 + i,
                "probabilities": [.6, .2, .2] if model == "poisson" else [.4, .2, .4],
                "source_authenticity_verified": False,
                "independently_timestamped": False,
            })
        runs[model] = {"status": "HOLD",
                       "reason": "PROSPECTIVE_SOURCE_AND_RESULT_ATTESTATION_MISSING",
                       "production_recommendations": "DISABLED",
                       "positive_ev_verified": False,
                       "independent_provenance_verified": False,
                       "refit_count": 2, "predictions": predictions}
    return {"schema": "football-king-paired-refit-score-v1",
            "results": results, "model_runs": runs}


class PairedScoreTests(unittest.TestCase):
    def test_same_fixtures_scored_research_only(self):
        report = score_paired(sample())
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["paired_fixture_count"], 2)
        self.assertEqual(report["unverified_diagnostic_metrics"]["poisson"]["sample_count"], 2)
        self.assertEqual(report["unverified_diagnostic_metrics"]["dixon_coles"]["sample_count"], 2)
        self.assertFalse(report["positive_ev_verified"])

    def test_missing_model_holds(self):
        data = sample()
        del data["model_runs"]["dixon_coles"]
        self.assertEqual(score_paired(data)["reason"], "MISSING_MODEL_RUN")

    def test_missing_fixture_holds(self):
        data = sample()
        data["model_runs"]["poisson"]["predictions"].pop()
        self.assertEqual(score_paired(data)["reason"], "MISSING_OR_EXTRA_PREDICTION")

    def test_duplicate_fixture_holds(self):
        data = sample()
        data["results"][1]["fixture_id"] = data["results"][0]["fixture_id"]
        self.assertEqual(score_paired(data)["reason"], "DUPLICATE_OR_INVALID_FIXTURE")

    def test_mismatched_cutoff_holds(self):
        data = sample()
        data["model_runs"]["dixon_coles"]["predictions"][0]["as_of_utc"] = "2026-11-08T17:00:00Z"
        self.assertEqual(score_paired(data)["reason"], "MODEL_CUTOFF_MISMATCH")

    def test_post_kickoff_forecast_holds(self):
        data = sample()
        data["model_runs"]["poisson"]["predictions"][0]["as_of_utc"] = "2026-11-08T21:00:00Z"
        self.assertEqual(score_paired(data)["reason"], "LOOKAHEAD")

    def test_false_external_certification_claim_holds(self):
        data = sample()
        data["model_runs"]["poisson"]["predictions"][0]["independently_timestamped"] = True
        self.assertEqual(score_paired(data)["reason"], "UNTRUSTED_PROVENANCE_CLAIM")

    def test_invalid_probability_holds(self):
        data = sample()
        data["model_runs"]["poisson"]["predictions"][0]["probabilities"] = [.9, .9, -.8]
        self.assertEqual(score_paired(data)["status"], "HOLD")
        self.assertNotIn("unverified_diagnostic_metrics", score_paired(data))

    def test_invalid_result_chronology_holds(self):
        data = sample()
        data["results"][0]["result_recorded_utc"] = "2026-11-08T19:00:00Z"
        self.assertEqual(score_paired(data)["reason"], "INVALID_RESULT_CHRONOLOGY")


if __name__ == "__main__":
    unittest.main()
