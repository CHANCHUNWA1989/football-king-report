"""Synthetic offline fixture-integrity tests."""
import tempfile
import unittest
from pathlib import Path
from ops.historical_fixture_integrity import audit_history


class HistoricalFixtureIntegrityTests(unittest.TestCase):
    def audit(self, body):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.csv"
            path.write_text("Date,HomeTeam,AwayTeam,FTHG,FTAG\n" + body, encoding="utf-8")
            return audit_history(path)

    def test_valid_rows(self):
        self.assertEqual(self.audit("24/10/2026,A,B,2,1\n")["status"], "OFFLINE_INTEGRITY_ONLY")

    def test_duplicate_fixture_hold(self):
        result = self.audit("24/10/2026,A,B,2,1\n24/10/2026,A,B,2,1\n")
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["duplicate_fixture_rows"], 1)

    def test_invalid_score_hold(self):
        self.assertEqual(self.audit("24/10/2026,A,B,-1,1\n")["status"], "HOLD")

    def test_empty_hold(self):
        self.assertEqual(self.audit("")["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
