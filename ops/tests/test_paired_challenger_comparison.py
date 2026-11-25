import unittest
from ops.paired_challenger_comparison import evaluate


def sample():
    return {"key": "synthetic-fixture-1", "kickoff_utc": "2026-11-08T20:00:00+00:00",
            "as_of_utc": "2026-11-08T18:00:00+00:00", "y": 0,
            "model_a": [.6, .2, .2], "challenger": [.7, .2, .1],
            "market": [.5, .3, .2], "independently_verified": True,
            "sealed_before_kickoff": True}


class PairedComparisonTests(unittest.TestCase):
    def test_synthetic_metrics_are_diagnostic_only_and_hold(self):
        r = evaluate([sample()])
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["reason"], "EXTERNAL_PROVENANCE_AND_QUOTE_ALIGNMENT_NOT_VERIFIED")
        self.assertLess(r["unverified_diagnostic_metrics"]["challenger"]["log_loss"],
                        r["unverified_diagnostic_metrics"]["model_a"]["log_loss"])
        self.assertFalse(r["model_promoted"])
        self.assertFalse(r["positive_ev_verified"])
        self.assertFalse(r["independent_provenance_verified"])

    def test_caller_claims_can_never_unlock_certification(self):
        r = sample()
        r["independently_verified"] = True
        r["sealed_before_kickoff"] = True
        result = evaluate([r])
        self.assertEqual(result["status"], "HOLD")
        self.assertNotIn("metrics", result)

    def test_unverified_fails_closed(self):
        r = sample()
        r["independently_verified"] = False
        self.assertEqual(evaluate([r])["reason"], "UNVERIFIED_OR_UNSEALED")

    def test_post_kickoff_fails_closed(self):
        r = sample()
        r["as_of_utc"] = "2026-11-08T21:00:00+00:00"
        self.assertEqual(evaluate([r])["reason"], "LOOKAHEAD")

    def test_duplicate_fails_entire_cohort(self):
        r = sample()
        self.assertEqual(evaluate([r, r])["reason"], "DUPLICATE_OR_INVALID_KEY")

    def test_invalid_probability_fails_closed(self):
        r = sample()
        r["challenger"] = [.9, .9, -.8]
        self.assertEqual(evaluate([r])["reason"], "INVALID_PROBABILITIES")

    def test_invalid_timezone_fails_closed(self):
        r = sample()
        r["as_of_utc"] = "2026-11-08T18:00:00"
        self.assertEqual(evaluate([r])["status"], "HOLD")

    def test_empty_hold(self):
        self.assertEqual(evaluate([])["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
