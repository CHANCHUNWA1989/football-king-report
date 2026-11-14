"""Deterministic quality reporting tests, with no external feeds."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_quality_report import summarize_admissions


class TestLiveQualityReport(unittest.TestCase):
    def test_mixed_decisions(self):
        decisions = [
            {"status": "RESEARCH_ONLY", "reason": "SYNCHRONIZED_RESEARCH",
             "production_recommendations": "DISABLED"},
            {"status": "HOLD", "reason": "STALE_SCORE",
             "production_recommendations": "DISABLED"},
            {"status": "HOLD", "reason": "STALE_SCORE",
             "production_recommendations": "DISABLED"},
        ]
        result = summarize_admissions(decisions)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["accepted_research"], 1)
        self.assertEqual(result["held"], 2)
        self.assertEqual(result["research_acceptance_rate"], 0.3333)
        self.assertEqual(result["hold_reasons"], {"STALE_SCORE": 2})
        self.assertFalse(result["positive_ev_verified"])

    def test_empty_batch_is_hold(self):
        result = summarize_admissions([])
        self.assertEqual(result["status"], "HOLD")
        self.assertIsNone(result["research_acceptance_rate"])

    def test_malformed_decision_holds(self):
        for batch in (None, {}, [None], [{"status": "PASS", "reason": "ok",
                         "production_recommendations": "DISABLED"}]):
            with self.subTest(batch=batch):
                self.assertEqual(summarize_admissions(batch)["status"], "HOLD")

    def test_unsafe_production_flag_holds(self):
        result = summarize_admissions([{"status": "RESEARCH_ONLY",
                 "reason": "SYNCHRONIZED_RESEARCH",
                 "production_recommendations": "ENABLED"}])
        self.assertEqual(result["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
