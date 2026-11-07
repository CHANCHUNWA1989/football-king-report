import copy
import unittest
from ops.private_model_comparison import compare


def sample(fixture="synthetic-1"):
    return {"fixture_id": fixture, "probabilities": {"H": 0.5, "D": 0.3, "A": 0.2},
            "outcome": "H", "prediction_utc": "2026-01-01T10:00:00Z",
            "kickoff_utc": "2026-01-01T12:00:00Z",
            "result_recorded_utc": "2026-01-01T15:00:00Z"}


class PairedComparisonTests(unittest.TestCase):
    def test_identical_models_have_zero_delta(self):
        rows = [sample(), sample("synthetic-2")]
        report = compare(rows, copy.deepcopy(rows))
        self.assertEqual(report["paired_fixture_count"], 2)
        self.assertEqual(report["log_loss_delta_dc_minus_poisson"], 0)
        self.assertEqual(report["brier_delta_dc_minus_poisson"], 0)
        self.assertFalse(report["model_promoted"])
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_better_dc_on_synthetic_outcome(self):
        a = [sample()]
        b = copy.deepcopy(a)
        b[0]["probabilities"] = {"H": 0.8, "D": 0.1, "A": 0.1}
        report = compare(a, b)
        self.assertLess(report["log_loss_delta_dc_minus_poisson"], 0)
        self.assertLess(report["brier_delta_dc_minus_poisson"], 0)
        self.assertFalse(report["positive_ev_verified"])

    def test_unpaired_fixture_rejected(self):
        with self.assertRaises(ValueError):
            compare([sample()], [sample("different")])

    def test_conflicting_result_rejected(self):
        a = [sample()]
        b = copy.deepcopy(a)
        b[0]["outcome"] = "A"
        with self.assertRaises(ValueError):
            compare(a, b)

    def test_conflicting_cutoff_rejected(self):
        a = [sample()]
        b = copy.deepcopy(a)
        b[0]["prediction_utc"] = "2026-01-01T11:00:00Z"
        with self.assertRaises(ValueError):
            compare(a, b)


if __name__ == "__main__":
    unittest.main()
