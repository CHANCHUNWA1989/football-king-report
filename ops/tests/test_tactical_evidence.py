import unittest
from ops.tactical_evidence import assess


class TacticalEvidenceTests(unittest.TestCase):
    NOW = "2026-10-28T10:45:00Z"

    def case(self):
        return {
            "fixture": {"event_id": "fixture-123"},
            "lineup": {"event_id": "fixture-123",
                       "official_source_authenticated": True,
                       "home_starters": [f"home-{i}" for i in range(11)],
                       "away_starters": [f"away-{i}" for i in range(11)]},
            "live_stats": {"event_id": "fixture-123",
                           "independently_verified": True,
                           "updated_at_utc": "2026-10-28T10:44:00Z",
                           "defensive_position_indicators": {
                               "source_authenticated": True,
                               "observed_minutes": 20,
                               "deep_block_minutes": 16}}
        }

    def test_sustained_low_block_research_only(self):
        r = assess(self.case(), now_utc=self.NOW)
        self.assertEqual(r["low_block_assessment"], "SUSTAINED_LOW_BLOCK_EVIDENCE")
        self.assertEqual(r["status"], "RESEARCH_ONLY")
        self.assertFalse(r["betting_permission"])

    def test_formation_alone_not_enough(self):
        c = self.case()
        del c["live_stats"]["defensive_position_indicators"]
        c["lineup"]["away_formation"] = "5-4-1"
        r = assess(c, now_utc=self.NOW)
        self.assertEqual(r["low_block_assessment"], "UNKNOWN")

    def test_stale_stats_hold(self):
        c = self.case()
        c["live_stats"]["updated_at_utc"] = "2026-10-28T10:35:00Z"
        self.assertIn("LIVE_STATS_STALE", assess(c, now_utc=self.NOW)["reasons"])

    def test_unverified_source_hold(self):
        c = self.case()
        c["live_stats"]["defensive_position_indicators"]["source_authenticated"] = False
        self.assertEqual(assess(c, now_utc=self.NOW)["status"], "HOLD")

    def test_five_back_never_proves_low_block(self):
        c = self.case()
        c["lineup"]["away_formation"] = "5-4-1"
        c["live_stats"]["defensive_position_indicators"]["deep_block_minutes"] = 3
        self.assertEqual(assess(c, now_utc=self.NOW)["low_block_assessment"],
                         "MIXED_OR_HIGHER_BLOCK_EVIDENCE")

    def test_mismatched_fixture_hold(self):
        c = self.case()
        c["live_stats"]["event_id"] = "another"
        self.assertIn("LIVE_STATS_UNVERIFIED", assess(c, now_utc=self.NOW)["reasons"])


if __name__ == "__main__":
    unittest.main()
