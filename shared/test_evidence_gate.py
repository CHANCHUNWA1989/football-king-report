import unittest
from shared.evidence_gate import evaluate_evidence

BASE = dict(system="football", probability=.6, decimal_odds=2.0,
            source="test-fixture", observed_at="2026-10-17T10:00:00+08:00",
            now="2026-10-17T10:01:00+08:00",
            verified_model=True, sample_size=200)

class EvidenceGateTests(unittest.TestCase):
    def test_fresh_verified_is_research_only(self):
        r = evaluate_evidence(**BASE)
        self.assertTrue(r["research_candidate"])
        self.assertFalse(r["live_execution_allowed"])
    def test_stale_rejected(self):
        r = evaluate_evidence(**dict(BASE, now="2026-10-17T10:20:00+08:00"))
        self.assertFalse(r["research_candidate"])
        self.assertIn("STALE_SOURCE", r["reasons"])
    def test_unverified_model_rejected(self):
        r = evaluate_evidence(**dict(BASE, verified_model=False))
        self.assertFalse(r["research_candidate"])
    def test_quant_needs_cost_risk_review(self):
        r = evaluate_evidence(**dict(BASE, system="quant", decimal_odds=None))
        self.assertFalse(r["research_candidate"])
    def test_future_timestamp_rejected(self):
        r = evaluate_evidence(**dict(BASE, now="2026-10-17T09:00:00+08:00"))
        self.assertFalse(r["research_candidate"])

if __name__ == "__main__":
    unittest.main()
