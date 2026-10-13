"""Tests for research-only manual HKJC market snapshot parser."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hkjc_snapshot_audit import validate


def sample():
    return {
        "source": "HKJC_MANUAL_SCREENSHOT", "market": "FT_1X2",
        "fixture_id": "FB6784",
        "captured_at_utc": "2026-10-13T07:35:00Z",
        "kickoff_utc": "2026-10-13T07:45:00Z",
        "odds": {"home": 3.75, "draw": 4.15, "away": 1.60},
    }


class SnapshotTests(unittest.TestCase):
    def test_actual_user_snapshot(self):
        result = validate(sample())
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertAlmostEqual(sum(result["market_probabilities"].values()), 1, places=5)
        self.assertGreater(result["market_probabilities"]["away"], 0.5)
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_reject_post_kickoff(self):
        row = sample()
        row["captured_at_utc"] = row["kickoff_utc"]
        with self.assertRaises(ValueError):
            validate(row)

    def test_reject_wrong_market(self):
        row = sample()
        row["market"] = "ASIAN_HANDICAP"
        with self.assertRaises(ValueError):
            validate(row)

    def test_reject_boolean_odds(self):
        row = sample()
        row["odds"]["home"] = True
        with self.assertRaises(ValueError):
            validate(row)


if __name__ == "__main__":
    unittest.main()
