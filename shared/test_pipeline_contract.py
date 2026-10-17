"""Cross-module research pipeline contract; uses fixtures, never live orders."""
import unittest
from shared.evidence_gate import evaluate_evidence
from shared.unified_prediction_evaluation import evaluate
from shared.execution_guard import authorize_execution

class PipelineContractTests(unittest.TestCase):
    def test_verified_candidate_settlement_and_live_lock(self):
        for system in ("football", "basketball"):
            with self.subTest(system=system):
                evidence = evaluate_evidence(
                    system=system, probability=0.6, decimal_odds=2.0,
                    source="fixture", observed_at="2026-10-17T10:00:00+08:00",
                    now="2026-10-17T10:01:00+08:00", verified_model=True,
                    verified_market_data=True, sample_size=200)
                self.assertTrue(evidence["research_candidate"])
                self.assertFalse(evidence["live_execution_allowed"])
                prediction = dict(prediction_id=system+"-1", system=system,
                    event_id="fixture-event", created_at="2026-10-17T10:01:00+08:00",
                    model_version="fixture-v1", market="binary", selection="yes",
                    probability=0.6, odds=2.0, status="RESEARCH_ONLY")
                outcome = dict(prediction_id=system+"-1", outcome=1,
                    actual_result_at="2026-10-17T12:00:00+08:00",
                    verified=True, source="fixture")
                report = evaluate([prediction], [outcome])
                self.assertEqual(report["evaluated"], 1)
                self.assertAlmostEqual(report["mean_brier"], 0.16)
                self.assertTrue(report["research_only"])
                proposal = dict(proposal_id="fixture", system=system,
                    mode="PAPER", created_at="2026-10-17T10:01:00+08:00",
                    expires_at="2026-10-17T12:00:00+08:00",
                    instrument="fixture", side="yes", amount=10)
                self.assertFalse(authorize_execution(proposal, approval=True)["allowed"])

    def test_stale_evidence_cannot_be_recommended(self):
        evidence = evaluate_evidence(system="football", probability=0.6,
            decimal_odds=2.0, source="fixture",
            observed_at="2026-10-17T10:00:00+08:00",
            now="2026-10-17T10:20:00+08:00", verified_model=True,
            verified_market_data=True, sample_size=200)
        self.assertFalse(evidence["research_candidate"])

    def test_quant_requires_risk_review_and_live_lock(self):
        evidence = evaluate_evidence(system="quant", probability=0.6,
            source="fixture", observed_at="2026-10-17T10:00:00+08:00",
            now="2026-10-17T10:01:00+08:00", verified_model=True,
            verified_market_data=True, sample_size=200)
        self.assertFalse(evidence["research_candidate"])
        self.assertFalse(evidence["live_execution_allowed"])

if __name__ == "__main__":
    unittest.main()
