"""Zero-network historical odds header audit tests."""
import unittest
from ops.historical_odds_header_audit import inspect_headers


class HistoricalOddsHeaderAuditTests(unittest.TestCase):
    def test_total_and_asian_candidates(self):
        result = inspect_headers("Date,HomeTeam,AwayTeam,FTHG,FTAG,B365>2.5,B365<2.5,AHh,B365AHH,B365AHA")
        self.assertEqual(result["status"], "SCHEMA_CANDIDATE_ONLY")
        self.assertIn("B365>2.5", result["totals_candidate_columns"])
        self.assertIn("AHh", result["asian_candidate_columns"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_missing_results_is_hold(self):
        self.assertEqual(inspect_headers("Date,HomeTeam,AwayTeam")["status"], "HOLD")

    def test_duplicate_header_is_hold(self):
        self.assertEqual(inspect_headers("Date,Date,HomeTeam,AwayTeam,FTHG,FTAG")["status"], "HOLD")

    def test_bom_header(self):
        self.assertEqual(inspect_headers("\ufeffDate,HomeTeam,AwayTeam,FTHG,FTAG")["status"],
                         "SCHEMA_CANDIDATE_ONLY")


if __name__ == "__main__":
    unittest.main()
