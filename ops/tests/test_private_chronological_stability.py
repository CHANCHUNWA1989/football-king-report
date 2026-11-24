import copy
import unittest
from datetime import datetime, timedelta, timezone
from ops.private_chronological_stability import evaluate


def cohort(n):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(n):
        kickoff = base + timedelta(days=i)
        rows.append({"fixture_id": "synthetic-" + str(i),
                     "probabilities": {"H": 0.5, "D": 0.3, "A": 0.2},
                     "outcome": "H",
                     "prediction_utc": (kickoff-timedelta(hours=2)).isoformat(),
                     "kickoff_utc": kickoff.isoformat(),
                     "result_recorded_utc": (kickoff+timedelta(hours=3)).isoformat()})
    return rows


class StabilityTests(unittest.TestCase):
    def test_small_cohort_fails_closed(self):
        rows = cohort(40)
        result = evaluate(rows, copy.deepcopy(rows))
        self.assertEqual(result["segment_status"], "INSUFFICIENT_CHRONOLOGICAL_SEGMENTS")
        self.assertEqual(result["segments"], [])
        self.assertFalse(result["model_promoted"])

    def test_equal_models_stay_inconclusive(self):
        rows = cohort(60)
        result = evaluate(list(reversed(rows)), copy.deepcopy(rows))
        self.assertEqual(result["segment_status"], "DESCRIPTIVE_ONLY")
        self.assertEqual([x["paired_fixture_count"] for x in result["segments"]], [30, 30])
        self.assertFalse(result["direction_consistent"])
        self.assertEqual(result["segments"][0]["log_loss_delta_dc_minus_poisson"], 0)

    def test_changing_direction_detected(self):
        rows = cohort(60)
        dc = copy.deepcopy(rows)
        for i, item in enumerate(dc):
            item["probabilities"] = ({"H": 0.8, "D": 0.1, "A": 0.1} if i < 30
                                     else {"H": 0.2, "D": 0.3, "A": 0.5})
        result = evaluate(rows, dc)
        self.assertFalse(result["direction_consistent"])
        self.assertLess(result["segments"][0]["log_loss_delta_dc_minus_poisson"], 0)
        self.assertGreater(result["segments"][1]["log_loss_delta_dc_minus_poisson"], 0)

    def test_mismatched_cohort_rejected(self):
        rows = cohort(60)
        with self.assertRaises(ValueError):
            evaluate(rows, rows[:-1])


if __name__ == "__main__":
    unittest.main()
