"""Regression tests for no-pick diagnostics and fallback safety."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_recommender import build


class ZeroSelectionDiagnosticsTests(unittest.TestCase):
    def test_no_pairs_explains_missing_recommendations(self):
        now = datetime(2026, 10, 10, 0, 0, tzinfo=timezone.utc)
        shadow = {"status": "SHADOW_ONLY", "production_recommendations": "DISABLED",
                  "as_of_utc": now.isoformat(), "predictions": []}
        pairing = {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
                   "comparisons": []}
        status = {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED"}
        result = build(shadow, pairing, status, now=now)
        self.assertEqual(result["selected_count"], 0)
        self.assertEqual(result["fallback_reason"], "NO_STRICT_MARKET_MATCHES")
        self.assertEqual(result["diagnostics"]["paired_total"], 0)
        self.assertIsNotNone(result["diagnostics"]["no_output_explanation"])
        self.assertEqual(result["production_recommendations"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
