"""Safety tests for the shadow-mode evidence gate."""
import csv
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_evidence import evaluate, publish, read_rows, probs


class ModelEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 9, 4, tzinfo=timezone.utc)
        self.kickoff = self.now + timedelta(days=1)
        self.row = {
            "case_id": "test_match_1",
            "prediction_utc": self.now.isoformat(),
            "market_utc": (self.now - timedelta(minutes=5)).isoformat(),
            "kickoff_utc": self.kickoff.isoformat(),
            "p_home": "0.6", "p_draw": "0.2", "p_away": "0.2",
            "m_home": "0.45", "m_draw": "0.3", "m_away": "0.25",
            "outcome": "home",
        }

    def write(self, path, rows):
        with path.open("w", encoding="utf-8", newline="") as f:
            wr = csv.DictWriter(f, fieldnames=list(self.row))
            wr.writeheader()
            wr.writerows(rows)

    def test_valid_baseline_scores_still_hold(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "forecasts.csv"
            self.write(f, [self.row])
            rows = read_rows(f)
            result = evaluate(rows)
            self.assertEqual(result["status"], "HOLD")
            self.assertGreater(result["measurements"]["market_minus_model_log_loss"], 0)
            self.assertFalse(result["immutable_forecast_evidence_verified"])

    def test_identical_sealed_cases_expose_model_home_bias_vs_market(self):
        cases = [
            {"kickoff":self.kickoff, "p":[.70,.20,.10], "m":[.25,.20,.55],"y":2},
            {"kickoff":self.kickoff+timedelta(days=1),
             "p":[.62,.18,.20], "m":[.36,.32,.32],"y":0},
            {"kickoff":self.kickoff+timedelta(days=2),
             "p":[.55,.25,.20], "m":[.20,.15,.65],"y":2},
        ]
        metrics=evaluate(cases)["measurements"]["directional_accuracy_audit"]
        self.assertEqual(metrics["n_same_settled_cases"],3)
        self.assertEqual(metrics["model_top_choice_correct"],1)
        self.assertEqual(metrics["market_top_choice_correct"],3)
        self.assertEqual(metrics["model_top_choice_home_count"],3)
        self.assertEqual(metrics["market_top_choice_home_count"],1)
        self.assertEqual(metrics["model_market_top_choice_agreements"],1)
        self.assertAlmostEqual(metrics["model_top_choice_rate"],1/3,places=5)
        self.assertEqual(metrics["market_top_choice_rate"],1.0)
        self.assertTrue(metrics["outcomes_not_independently_authenticated"])
        self.assertFalse(metrics["statistically_validated_advantage"])
        self.assertTrue(metrics["does_not_certify_future_hit_rate_or_profitability"])

    def test_empty_samples_never_report_accuracy(self):
        self.assertIsNone(evaluate([])["measurements"])

    def test_unverified_forecasts_keep_outcomes_unauthenticated(self):
        row = {"kickoff": self.kickoff, "p": [.6, .2, .2],
               "m": [.45, .3, .25], "y": 0}
        result = evaluate([row])
        self.assertFalse(result["immutable_forecast_evidence_verified"])
        self.assertTrue(result["measurements"]["directional_accuracy_audit"]
                        ["outcomes_not_independently_authenticated"])
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_verified_forecast_provenance_does_not_authenticate_outcomes(self):
        row = {"kickoff": self.kickoff, "p": [.6, .2, .2],
               "m": [.45, .3, .25], "y": 0}
        unverified = evaluate([row])
        result = evaluate([row], immutable_evidence=True)
        self.assertTrue(result["immutable_forecast_evidence_verified"])
        self.assertTrue(result["measurements"]["directional_accuracy_audit"]
                        ["outcomes_not_independently_authenticated"])
        self.assertEqual(result["measurements"], unverified["measurements"])
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["certified_profitable_model"])

    def test_prediction_after_kickoff_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "forecasts.csv"
            row = {**self.row, "prediction_utc": (self.kickoff + timedelta(minutes=2)).isoformat()}
            self.write(f, [row])
            with self.assertRaises(ValueError):
                read_rows(f)

    def test_market_baseline_after_prediction_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "forecasts.csv"
            row = {**self.row, "market_utc": (self.now + timedelta(minutes=1)).isoformat()}
            self.write(f, [row])
            with self.assertRaises(ValueError):
                read_rows(f)

    def test_bad_probabilities_rejected(self):
        with self.assertRaises(ValueError):
            probs({**self.row, "p_home": "0.9"}, "p")

    def test_duplicate_case_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "forecasts.csv"
            self.write(f, [self.row, self.row])
            with self.assertRaises(ValueError):
                read_rows(f)

    def test_missing_real_predictions_keep_hold(self):
        with tempfile.TemporaryDirectory() as d:
            site = Path(d) / "site"
            site.mkdir()
            (site / "index.html").write_text('<h2>七大缺口狀態</h2>', encoding="utf-8")
            result = publish(site, str(Path(d) / "missing.csv"))
            self.assertEqual(result["reason"], "NO_VERIFIED_POINT_IN_TIME_PREDICTIONS")
            self.assertEqual(result["status"], "HOLD")
            self.assertIn('shadow-validation', (site / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
