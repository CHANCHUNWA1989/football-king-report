"""EV evidence gate smoke/regression tests; run with ops on PYTHONPATH."""
import unittest
from ev_evidence_gate import audit_1x2

Q = {"decimal_odds": 2.1, "market_updated_utc": "2026-10-16T10:00:00Z",
     "captured_utc": "2026-10-16T10:05:00Z", "kickoff_utc": "2026-10-16T13:00:00Z",
     "source": "test", "executable": True}
F = {"probability": 0.51, "prediction_utc": "2026-10-16T10:06:00Z",
     "calibrated": True, "independent_of_market": True, "out_of_sample_verified": True}

class GateTests(unittest.TestCase):
    def test_positive_research_only(self):
        r = audit_1x2(Q, F)
        self.assertTrue(r["qualifies_for_research"])
        self.assertEqual(r["production_recommendations"], "DISABLED")

    def test_no_calibration(self):
        self.assertEqual(audit_1x2(Q, dict(F, calibrated=False))["reason"], "MODEL_EVIDENCE_MISSING")

    def test_stale_quote(self):
        self.assertEqual(audit_1x2(dict(Q, market_updated_utc="2026-10-16T08:00:00Z"), F)["reason"], "STALE_QUOTE")

    def test_future_quote(self):
        self.assertEqual(audit_1x2(dict(Q, captured_utc="2026-10-16T10:07:00Z"), F)["reason"], "CHRONOLOGY_FAILURE")

    def test_low_ev(self):
        self.assertEqual(audit_1x2(dict(Q, decimal_odds=1.9), F)["reason"], "EV_BELOW_THRESHOLD")

    def test_bad_numeric(self):
        self.assertEqual(audit_1x2(dict(Q, decimal_odds=float("nan")), F)["status"], "HOLD")
