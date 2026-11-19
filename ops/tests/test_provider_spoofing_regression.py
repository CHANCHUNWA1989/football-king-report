"""Adversarial regression: names and distinct payload hashes are not provenance.

Synthetic fixtures/results only. This module must never certify live results.
Run: python -m unittest ops.tests.test_provider_spoofing_regression -v
"""
import unittest

from ops.tests.test_forward_goal_candidate_settlement import make_snapshot, obs, evaluate


class ProviderSpoofingRegression(unittest.TestCase):
    def test_two_distinct_names_and_hashes_are_not_independent_certification(self):
        result = evaluate(make_snapshot(), [
            obs("official-looking-source", hash_letter="b"),
            obs("independent-looking-source", hash_letter="c"),
        ])
        fixture = result["fixtures"][0]
        self.assertEqual(fixture["settlement_state"], "MATCHED_TWO_PROVIDER_NAMES_UNVERIFIED")
        self.assertEqual(fixture["candidate_score_ft"], [2, 1])
        self.assertEqual(result["certified_independent_forward_cases"], 0)
        self.assertFalse(result["official_final_result_independently_verified"])
        self.assertFalse(result["eligible_for_model_promotion"])
        self.assertFalse(result["positive_ev_verified"])
        self.assertFalse(result["automated_betting_enabled"])
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_conflicting_third_source_blocks_candidate_scoring(self):
        result = evaluate(make_snapshot(), [
            obs("source-a", hash_letter="b"),
            obs("source-b", hash_letter="c"),
            obs("source-c", score=(1, 1), hash_letter="d"),
        ])
        self.assertEqual(result["fixtures"][0]["settlement_state"],
                         "CONFLICTING_FINAL_SCORES_HOLD")
        self.assertIsNone(result["fixtures"][0]["candidate_score_ft"])
        self.assertEqual(result["paired_market_diagnostics"]["over25"]["candidate_scored"], 0)
        self.assertEqual(result["certified_independent_forward_cases"], 0)


if __name__ == "__main__":
    unittest.main()
