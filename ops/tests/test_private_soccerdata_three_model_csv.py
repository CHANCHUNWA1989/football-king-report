import os
import tempfile
import unittest
from ops.private_soccerdata_three_model_csv import compare_three_models_csv


class ThreeModelCsvTests(unittest.TestCase):
    def setUp(self):
        f = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".csv", delete=False)
        self.path = f.name
        self.addCleanup(lambda: os.unlink(self.path))
        f.write("Date,HomeTeam,AwayTeam,FTHG,FTAG\n")
        for day, h, a in [(1, 1, 0), (1, 0, 1), (2, 0, 0), (3, 1, 1)]:
            f.write(f"2026-01-{day:02d},A,B,{h},{a}\n")
        f.close()

    def test_three_model_scores_identical_holdout(self):
        r = compare_three_models_csv(self.path, min_train=2, test_days=1)
        self.assertEqual(r["fixture_count"], 2)
        for key in ("frequency_baseline", "fitted_team_poisson", "approximate_dixon_coles"):
            self.assertIn("log_loss", r[key])
            self.assertIn("multiclass_brier_score", r[key])
        self.assertFalse(r["model_promoted"])
        self.assertFalse(r["positive_ev_verified"])

    def test_deterministic(self):
        self.assertEqual(compare_three_models_csv(self.path, min_train=2),
                         compare_three_models_csv(self.path, min_train=2))

    def test_insufficient_training(self):
        r = compare_three_models_csv(self.path, min_train=100)
        self.assertEqual(r["status"], "HOLD")

    def test_bad_csv_rejected(self):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write("2026-01-04,A,B,99,1\n")
        with self.assertRaisesRegex(ValueError, "INVALID_CSV_SCORE"):
            compare_three_models_csv(self.path, min_train=2)


if __name__ == "__main__":
    unittest.main()
