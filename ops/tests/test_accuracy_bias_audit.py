"""Regression tests for descriptive accuracy and home-bias audit."""
import sys
import tempfile
import csv
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from accuracy_bias_audit import audit


def sample(p, m, y, league="epl"):
    return {"p": p, "m": m, "y": y, "league": league}


class AccuracyBiasAuditTests(unittest.TestCase):
    def test_empty_is_hold(self):
        result = audit([])
        self.assertEqual(result["status"], "HOLD")
        self.assertIsNone(result["model_accuracy"])
        self.assertFalse(result["qualifies_for_betting"])

    def test_model_market_same_cases(self):
        rows = [
            sample([.6, .2, .2], [.2, .2, .6], 2),
            sample([.6, .2, .2], [.2, .6, .2], 1),
            sample([.6, .2, .2], [.6, .2, .2], 0),
        ]
        result = audit(rows)
        self.assertEqual(result["n"], 3)
        self.assertEqual(result["model_correct"], 1)
        self.assertEqual(result["market_correct"], 3)
        self.assertEqual(result["predicted_counts"]["model"]["home"], 3)
        self.assertEqual(result["actual_counts"]["home"], 1)
        self.assertFalse(result["home_bias_review_flag"])  # minimum sample safeguard
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_bias_flag_requires_twenty_settled_rows(self):
        rows = [sample([.7, .2, .1], [.2, .5, .3], 1) for _ in range(20)]
        result = audit(rows)
        self.assertTrue(result["home_bias_review_flag"])
        self.assertEqual(result["model_home_pick_share"], 1)
        self.assertEqual(result["actual_home_win_share"], 0)

    def test_reject_invalid_probabilities(self):
        with self.assertRaises(ValueError):
            audit([sample([.8, .8, -.6], [.2, .3, .5], 0)])
        with self.assertRaises(ValueError):
            audit([sample([float("nan"), .2, .8], [.2, .3, .5], 0)])

    def test_reject_invalid_outcome(self):
        with self.assertRaises(ValueError):
            audit([sample([.5, .3, .2], [.2, .3, .5], True)])

    def test_sealed_csv_preserves_league(self):
        from model_evidence import read_rows
        from pathlib import Path
        fields = ["case_id", "prediction_utc", "market_utc", "kickoff_utc", "p_home", "p_draw", "p_away", "m_home", "m_draw", "m_away", "outcome", "league"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerow(dict(zip(fields, ["1", "2026-10-10T10:00:00Z", "2026-10-10T09:00:00Z", "2026-10-10T12:00:00Z", ".5", ".3", ".2", ".4", ".3", ".3", "home", "epl"])))
            rows = read_rows(path)
        self.assertEqual(rows[0]["league"], "epl")
        self.assertEqual(audit(rows)["by_league"]["epl"]["n"], 1)

    def test_unknown_league_does_not_break(self):
        row = sample([.5, .3, .2], [.2, .3, .5], 0, "")
        self.assertEqual(audit([row])["by_league"]["unknown"]["n"], 1)


if __name__ == "__main__":
    unittest.main()
