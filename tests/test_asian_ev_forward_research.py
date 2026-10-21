"""Tests for evidence-gated, one-fixture-per-selection research ROI."""
import unittest
from ops.asian_ev_forward_research import evaluate_settled

def row(**changes):
    r = dict(fixture_id="f1", provider="licensed-source",
             market="totals", selection="over", provider_quote_id="q1",
             evidence_uri="https://example.org/record/q1",
             settlement_basis="FULL_MATCH", market_phase="PREMATCH",
             price_was_executable=True,
             quote_utc="2026-10-20T17:00:00Z",
             decision_utc="2026-10-20T17:01:00Z",
             kickoff_utc="2026-10-20T18:00:00Z",
             settlement_utc="2026-10-20T20:00:00Z",
             margin=3, line=-2.75, decimal_odds=1.65, model_ev=0.04)
    r.update(changes)
    return r

class ForwardResearchTests(unittest.TestCase):
    def test_settled_half_win(self):
        r = evaluate_settled([row()])
        self.assertAlmostEqual(r["roi_per_unit"], .325)
        self.assertEqual(r["unique_fixture_count"], 1)
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertFalse(r["positive_ev_verified"])
        self.assertFalse(r["evidence_independently_verified"])

    def test_empty(self):
        self.assertIsNone(evaluate_settled([])["roi_per_unit"])

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_settled([row(), row()])

    def test_future_quote_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_settled([row(quote_utc="2026-10-20T18:10:00Z")])

    def test_missing_settlement_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_settled([row(settlement_utc="2026-10-20T17:30:00Z")])

    def test_missing_evidence_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_settled([row(evidence_uri="")])

    def test_unverified_executable_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_settled([row(price_was_executable=False)])

    def test_inplay_rejected_until_settlement_supported(self):
        with self.assertRaises(ValueError):
            evaluate_settled([row(market_phase="INPLAY", match_minute=10,
                                  home_goals=0, away_goals=0,
                                  quote_utc="2026-10-20T18:10:00Z",
                                  decision_utc="2026-10-20T18:11:00Z")])

    def test_second_quote_same_fixture_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_settled([row(), row(provider_quote_id="q2",
                                         quote_utc="2026-10-20T17:05:00Z",
                                         decision_utc="2026-10-20T17:06:00Z")])

    def test_second_market_same_fixture_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_settled([row(), row(provider_quote_id="q3",
                                         market="handicap", selection="home")])

    def test_distinct_fixture_accepted(self):
        r = evaluate_settled([row(), row(fixture_id="f2", provider_quote_id="q2")])
        self.assertEqual(r["sample_count"], 2)
        self.assertEqual(r["unique_fixture_count"], 2)

if __name__ == "__main__":
    unittest.main()
