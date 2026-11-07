import os
import tempfile
import unittest
from ops.private_soccerdata_csv_poisson_comparison import run_csv_poisson_comparison


class CsvPoissonComparisonTests(unittest.TestCase):
    def setUp(self):
        f = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".csv", delete=False)
        self.path = f.name
        self.addCleanup(lambda: os.unlink(self.path))
        f.write("Date,HomeTeam,AwayTeam,FTHG,FTAG\n")
        for day, score in [(1, "2,0"), (1, "1,1"), (2, "0,1"), (3, "2,1")]:
            f.write(f"2026-01-{day:02d},A,B,{score}\n")
        f.close()

    def test_end_to_end_paired_models(self):
        report = run_csv_poisson_comparison(self.path, min_train=2, test_days=1)
        self.assertEqual(report["fixture_count"], 2)
        self.assertEqual(report["fold_count"], 2)
        self.assertIn("log_loss", report["fitted_team_poisson"])
        self.assertIn("log_loss", report["frequency_baseline"])
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertFalse(report["positive_ev_verified"])

    def test_deterministic(self):
        self.assertEqual(run_csv_poisson_comparison(self.path, min_train=2),
                         run_csv_poisson_comparison(self.path, min_train=2))

    def test_no_holdout(self):
        report = run_csv_poisson_comparison(self.path, min_train=100)
        self.assertEqual(report["status"], "HOLD")
        self.assertFalse(report["model_promoted"])

    def test_invalid_score_rejected(self):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write("2026-01-04,A,B,INVALID,0\n")
        with self.assertRaisesRegex(ValueError, "INVALID_CSV_SCORE"):
            run_csv_poisson_comparison(self.path, min_train=2)


if __name__ == "__main__":
    unittest.main()
