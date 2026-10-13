"""Reject malformed numerical probabilities from verification exports."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verification_slate import _make_row


class VerificationNumericalGuardTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            "production_recommendations": "DISABLED",
            "executable_market_odds_available": False,
            "value_bet_verified": False,
            "qualifies_for_value_recommendation": False,
            "suggested_stake": None,
            "reliability": "UNCALIBRATED_RESEARCH_ONLY",
            "league": "epl", "direction": "HOME",
            "kickoff_utc": "2026-10-20T15:00:00+00:00",
            "prediction_utc": "2026-10-19T15:00:00+00:00",
            "market_snapshot_utc": "2026-10-19T14:00:00+00:00",
            "market_updated_utc": "2026-10-19T13:00:00+00:00",
            "model_probability_1x2": [.5, .3, .2],
            "market_consensus_1x2": [.4, .3, .3],
            "case_id": "test-case", "home": "A", "away": "B",
            "research_probability": .5,
            "market_direction_agrees": True,
        }

    def test_rejects_nonfinite_model(self):
        for bad in (float("nan"), float("inf"), -0.1, 1.1):
            with self.subTest(bad=bad):
                row = dict(self.row, model_probability_1x2=[bad, .3, .2])
                with self.assertRaises(ValueError):
                    _make_row(row, "A_RESEARCH")

    def test_rejects_nonfinite_market(self):
        row = dict(self.row, market_consensus_1x2=[float("nan"), .3, .3])
        with self.assertRaises(ValueError):
            _make_row(row, "A_RESEARCH")

    def test_rejects_nonfinite_selected_probability(self):
        row = dict(self.row, research_probability=float("nan"))
        with self.assertRaises(ValueError):
            _make_row(row, "A_RESEARCH")


if __name__ == "__main__":
    unittest.main()
