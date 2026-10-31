import unittest
from research.market_gate import evaluate_research_market

class MarketGateTests(unittest.TestCase):
    def test_brentford_over_rejected(self):
        r = evaluate_research_market(reference_price=1.73, minimum_price=1.85,
            probability_range=[56, 61])
        self.assertIn("BELOW_RECONSIDERATION_THRESHOLD", r.reasons)
        self.assertFalse(r.certified_positive_ev)
        self.assertEqual(r.production_recommendations, "DISABLED")

    def test_rayo_under_rejected(self):
        r = evaluate_research_market(reference_price=1.81, minimum_price=2.00,
            probability_range=[51.1, 61.48])
        self.assertIn("MODEL_DISAGREEMENT_10PP", r.reasons)
        self.assertIn("BELOW_RECONSIDERATION_THRESHOLD", r.reasons)

    def test_no_price_never_approved(self):
        r = evaluate_research_market(reference_price=None, minimum_price=1.9,
            probability_range=[60, 65])
        self.assertEqual(r.status, "HOLD")

    def test_even_qualified_inputs_do_not_enable_betting(self):
        r = evaluate_research_market(reference_price=2.1, minimum_price=2.0,
            probability_range=[60, 63], quote_executable=True,
            quote_timestamp="2026-10-31T12:00:00Z", calibrated=True,
            official_sealed_prediction=True)
        self.assertFalse(r.certified_positive_ev)
        self.assertEqual(r.production_recommendations, "DISABLED")

if __name__ == "__main__":
    unittest.main()
