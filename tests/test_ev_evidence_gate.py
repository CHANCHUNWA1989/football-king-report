"""Regression checks for research-only EV gate."""
import unittest
from ops.ev_evidence_gate import audit_1x2

Q = dict(decimal_odds=2.1, market_updated_utc="2026-10-16T10:00:00Z",
         captured_utc="2026-10-16T10:05:00Z",
         kickoff_utc="2026-10-16T13:00:00Z",
         source="test-book", executable=True)
F = dict(probability=0.51, prediction_utc="2026-10-16T10:06:00Z",
         calibrated=True, independent_of_market=True,
         out_of_sample_verified=True)

class TestEvEvidenceGate(unittest.TestCase):
    def test_threshold_research_only(self):
        r = audit_1x2(Q, F)
        self.assertTrue(r["qualifies_for_research"])
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertEqual(r["status"], "RESEARCH_ONLY")

    def test_no_calibration_holds(self):
        r = audit_1x2(Q, dict(F, calibrated=False))
        self.assertEqual(r["reason"], "MODEL_EVIDENCE_MISSING")
        self.assertIsNone(r["ev"])

    def test_stale_quote_holds(self):
        r = audit_1x2(dict(Q, market_updated_utc="2026-10-16T08:00:00Z"), F)
        self.assertEqual(r["reason"], "STALE_QUOTE")

    def test_future_price_holds(self):
        r = audit_1x2(dict(Q, captured_utc="2026-10-16T10:07:00Z"), F)
        self.assertEqual(r["reason"], "CHRONOLOGY_FAILURE")

    def test_below_threshold(self):
        r = audit_1x2(dict(Q, decimal_odds=1.9), F)
        self.assertEqual(r["reason"], "EV_BELOW_THRESHOLD")
        self.assertFalse(r["qualifies_for_research"])

    def test_nan_holds(self):
        r = audit_1x2(dict(Q, decimal_odds=float("nan")), F)
        self.assertEqual(r["status"], "HOLD")

if __name__ == "__main__":
    unittest.main()
