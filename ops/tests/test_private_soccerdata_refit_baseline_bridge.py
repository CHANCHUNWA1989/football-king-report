import unittest
from unittest.mock import patch
from ops.private_soccerdata_refit_baseline_bridge import compare_refit_reports_to_baseline


def report(model):
    return {"status": "HOLD", "reason": "PROSPECTIVE_SOURCE_AND_RESULT_ATTESTATION_MISSING",
            "production_recommendations": "DISABLED",
            "independent_provenance_verified": False, "positive_ev_verified": False,
            "refit_count": 1, "predictions": [{
                "fixture_id": "3", "kickoff_utc": "2026-01-02T12:00:00Z",
                "as_of_utc": "2026-01-01T12:00:00Z",
                "model_id": "penaltyblog-" + model + "-offline-challenger-v1",
                "training_match_count": 30, "probabilities": [.4, .3, .3],
                "source_authenticity_verified": False,
                "independently_timestamped": False}]}


class RefitBridgeTests(unittest.TestCase):
    def setUp(self):
        self.history = [{"source_index": "3", "outcome": "H"}]

    @patch("ops.private_soccerdata_refit_baseline_bridge.compare_to_frequency_baseline")
    def test_both_models_share_baseline(self, compare):
        compare.return_value = {"status": "RESEARCH_ONLY", "fixture_count": 1,
                                "baseline": {"log_loss": 1.0},
                                "challenger": {"log_loss": .9},
                                "log_loss_delta_challenger_minus_baseline": -.1}
        result = compare_refit_reports_to_baseline(self.history, report("poisson"),
                                                   report("dixon_coles"))
        self.assertEqual(compare.call_count, 2)
        self.assertFalse(result["model_promoted"])

    def test_wrong_model_rejected(self):
        with self.assertRaisesRegex(ValueError, "INVALID_REFIT_PREDICTION"):
            compare_refit_reports_to_baseline(self.history, report("dixon_coles"),
                                              report("dixon_coles"))

    def test_fake_attestation_rejected(self):
        a = report("poisson")
        a["independent_provenance_verified"] = True
        with self.assertRaisesRegex(ValueError, "UNTRUSTED"):
            compare_refit_reports_to_baseline(self.history, a, report("dixon_coles"))

    def test_mismatched_ids_rejected(self):
        a = report("poisson")
        a["predictions"][0]["fixture_id"] = "other"
        with self.assertRaisesRegex(ValueError, "UNPAIRED"):
            compare_refit_reports_to_baseline(self.history, a, report("dixon_coles"))


if __name__ == "__main__":
    unittest.main()
