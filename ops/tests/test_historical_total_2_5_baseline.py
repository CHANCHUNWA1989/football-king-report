"""Local-only baseline regression tests with synthetic fixtures."""
import tempfile
import unittest
from pathlib import Path
from ops.historical_total_2_5_baseline import analyze_csv


class HistoricalTotal25BaselineTests(unittest.TestCase):
    def test_synthetic_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.csv"
            path.write_text("Date,HomeTeam,AwayTeam,FTHG,FTAG,B365>2.5,B365<2.5\n"
                            "24/10/2026,Home,Away,2,1,1.90,1.95\n"
                            "24/10/2026,Other,Side,0,1,1.80,2.05\n", encoding="utf-8")
            result = analyze_csv(path)
            self.assertEqual(result["valid_rows"], 2)
            self.assertEqual(result["status"], "HISTORICAL_BASELINE_ONLY")
            self.assertEqual(result["model_predictions_evaluated"], 0)

    def test_no_valid_rows_is_hold(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.csv"
            path.write_text("Date,HomeTeam,AwayTeam,FTHG,FTAG,B365>2.5,B365<2.5\n"
                            "24/10/2026,Home,Away,,,1.90,1.95\n", encoding="utf-8")
            self.assertEqual(analyze_csv(path)["status"], "HOLD")

    def test_missing_columns_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text("Date,HomeTeam\n24/10/2026,Home\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "MISSING_REQUIRED_COLUMNS"):
                analyze_csv(path)


if __name__ == "__main__":
    unittest.main()
