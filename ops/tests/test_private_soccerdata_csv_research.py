import os
import tempfile
import unittest
from ops.private_soccerdata_csv_research import import_settled_csv
from ops.private_soccerdata_research_cli import run


class CsvResearchTests(unittest.TestCase):
    def setUp(self):
        self.file = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".csv", delete=False)
        self.addCleanup(lambda: os.unlink(self.file.name))
        self.file.write("Date,HomeTeam,AwayTeam,FTHG,FTAG\n")
        self.file.write("2026-01-01,A,B,2,1\n")
        self.file.write("2026-01-01,C,D,0,0\n")
        self.file.write("2026-01-02,E,F,0,3\n")
        self.file.close()

    def test_real_csv_parsing_and_baseline_report(self):
        payload = import_settled_csv(self.file.name, min_train=2, test_days=1)
        self.assertEqual(payload["records"][0]["outcome"], "H")
        self.assertTrue(payload["records"][0]["date_only_calendar_marker"])
        self.assertIsNone(payload["records"][0]["kickoff_utc"])
        result = run(payload)
        self.assertEqual(result["baseline"]["prediction_count"], 1)
        self.assertFalse(result["independent_provenance_verified"])

    def test_invalid_date_rejected(self):
        with open(self.file.name, "a", encoding="utf-8") as f:
            f.write("01/01/26,G,H,1,0\n")
        with self.assertRaisesRegex(ValueError, "INVALID_CSV_DATE"):
            import_settled_csv(self.file.name)

    def test_invalid_score_rejected(self):
        with open(self.file.name, "a", encoding="utf-8") as f:
            f.write("2026-01-03,G,H,2.5,0\n")
        with self.assertRaisesRegex(ValueError, "INVALID_CSV_SCORE"):
            import_settled_csv(self.file.name)

    def test_row_limit_rejected(self):
        with self.assertRaisesRegex(ValueError, "CSV_ROW_LIMIT_EXCEEDED"):
            import_settled_csv(self.file.name, max_rows=2)


if __name__ == "__main__":
    unittest.main()
