"""Verify unified research distinguishes absent input and empty settled data."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unified_research import run


class UnifiedResearchCoverageTests(unittest.TestCase):
    def test_missing_input_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            result = run(Path(d) / "missing.csv")
            self.assertEqual(result["reason"], "NO_SEALED_PREDICTIONS")
            self.assertFalse(result["has_sealed_input"])
            self.assertEqual(result["settled_comparable_matches"], 0)
            self.assertEqual(result["status"], "HOLD")

    def test_header_only_input_is_not_treated_as_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "empty.csv"
            path.write_text("case_id,prediction_utc,market_utc,kickoff_utc,p_home,p_draw,p_away,m_home,m_draw,m_away,outcome\n", encoding="utf-8")
            result = run(path)
            self.assertTrue(result["has_sealed_input"])
            self.assertEqual(result["settled_comparable_matches"], 0)
            self.assertEqual(result["reason"], "NO_SETTLED_COMPARABLE_MATCHES")
            self.assertEqual(result["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
