import copy
import unittest
from datetime import datetime, timedelta, timezone
from ops.private_forecast_snapshot import seal
from ops.private_sealed_backtest import evaluate_sealed


def fixtures(n=60):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    poisson, dc, outcomes = [], [], []
    for i in range(n):
        kickoff = start + timedelta(days=i)
        row = {"fixture_id": "synthetic-" + str(i), "model": "poisson",
               "model_version": "synthetic-v1",
               "prediction_utc": (kickoff-timedelta(hours=2)).isoformat(),
               "kickoff_utc": kickoff.isoformat(),
               "probabilities": {"H": 0.5, "D": 0.3, "A": 0.2},
               "production_recommendations": "DISABLED"}
        poisson.append(seal(row))
        changed = copy.deepcopy(row)
        changed["model"] = "dixon_coles"
        dc.append(seal(changed))
        outcomes.append({"fixture_id": row["fixture_id"], "kickoff_utc": row["kickoff_utc"],
                         "outcome": "H",
                         "result_recorded_utc": (kickoff+timedelta(hours=3)).isoformat()})
    return poisson, dc, outcomes


class SealedBacktestTests(unittest.TestCase):
    def test_full_sealed_pipeline(self):
        a, b, results = fixtures()
        report = evaluate_sealed(a, b, results)
        self.assertEqual(report["segment_status"], "DESCRIPTIVE_ONLY")
        self.assertEqual(report["paired_fixture_count"], 60)
        self.assertEqual(report["overall"]["log_loss_delta_dc_minus_poisson"], 0)
        self.assertFalse(report["source_capture_independently_attested"])
        self.assertFalse(report["model_promoted"])

    def test_tampered_snapshot_rejected(self):
        a, b, results = fixtures(2)
        a[0]["forecast"]["probabilities"]["H"] = 0.6
        with self.assertRaises(ValueError):
            evaluate_sealed(a, b, results)

    def test_unmatched_outcome_rejected(self):
        a, b, results = fixtures(2)
        with self.assertRaises(ValueError):
            evaluate_sealed(a, b, results[:-1])

    def test_result_before_kickoff_rejected(self):
        a, b, results = fixtures(2)
        results[0]["result_recorded_utc"] = results[0]["kickoff_utc"]
        with self.assertRaises(ValueError):
            evaluate_sealed(a, b, results)

    def test_inconsistent_model_cutoff_rejected(self):
        a, b, results = fixtures(2)
        row = copy.deepcopy(b[0]["forecast"])
        row["prediction_utc"] = (datetime.fromisoformat(row["prediction_utc"])+timedelta(minutes=1)).isoformat()
        b[0] = seal(row)
        with self.assertRaises(ValueError):
            evaluate_sealed(a, b, results)


if __name__ == "__main__":
    unittest.main()
