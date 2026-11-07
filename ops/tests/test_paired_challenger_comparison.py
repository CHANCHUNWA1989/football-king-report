import unittest
from ops.paired_challenger_comparison import evaluate


def sample():
    return {"key": "synthetic-fixture-1", "kickoff_utc": "2026-11-08T20:00:00+00:00",
            "as_of_utc": "2026-11-08T18:00:00+00:00", "y": 0,
            "model_a": [.6, .2, .2], "challenger": [.7, .2, .1],
            "market": [.5, .3, .2], "independently_verified": True,
            "sealed_before_kickoff": True}


class PairedComparisonTests(unittest.TestCase):
    def test_valid_synthetic_cohort(self):
        r = evaluate([sample()])
        self.assertEqual(r["status"], "RESEARCH_ONLY")
        self.assertLess(r["metrics"]["challenger"]["log_loss"],
                        r["metrics"]["model_a"]["log_loss"])
        self.assertFalse(r["model_promoted"])

    def test_unverified_fails_closed(self):
        r = sample()
        r["independently_verified"] = False
        self.assertEqual(evaluate([r])["status"], "HOLD")

    def test_post_kickoff_fails_closed(self):
        r = sample()
        r["as_of_utc"] = "2026-11-08T21:00:00+00:00"
        self.assertEqual(evaluate([r])["status"], "HOLD")

    def test_duplicate_fails_entire_cohort(self):
        r = sample()
        self.assertEqual(evaluate([r, r])["status"], "HOLD")

    def test_invalid_probability_fails_closed(self):
        r = sample()
        r["challenger"] = [.9, .9, -.8]
        self.assertEqual(evaluate([r])["status"], "HOLD")

    def test_empty_hold(self):
        self.assertEqual(evaluate([])["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
