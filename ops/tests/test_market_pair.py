"""Strict same-fixture, strictly earlier market snapshot; never infer from aliases."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_pair import pair, identity


class MarketPairTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 9, 10, tzinfo=timezone.utc)
        self.kickoff = (self.now + timedelta(days=2)).isoformat()
        self.forecast = {"league": "epl", "home": "Everton", "away": "Arsenal",
                         "kickoff_utc": self.kickoff, "prediction_utc": self.now.isoformat(),
                         "p_home": .2, "p_draw": .3, "p_away": .5,
                         "production_recommendations": "DISABLED"}
        self.snapshot = {"status": "SHADOW_ONLY", "as_of_utc": self.now.isoformat(),
                         "predictions": [self.forecast],
                         "production_recommendations": "DISABLED"}
        self.price = {"league": "epl", "home": "Everton", "away": "Arsenal",
                      "source_event_id": "soccer-key-1", "kickoff_utc": self.kickoff,
                      "market_last_update_utc": (self.now - timedelta(minutes=15)).isoformat(),
                      "contributing_bookmakers": 4,
                      "p_home": .3, "p_draw": .3, "p_away": .4}
        self.market = {"status": "RESEARCH_ONLY",
                       "as_of_utc": (self.now - timedelta(minutes=10)).isoformat(),
                       "events": [self.price], "production_recommendations": "DISABLED"}

    def test_preexisting_exact_event_pairs(self):
        o = pair(self.snapshot, self.market)
        self.assertEqual(o["matched_count"], 1)
        self.assertEqual(o["status"], "RESEARCH_ONLY")
        self.assertFalse(o["comparisons"][0]["available_for_betting"])
        self.assertEqual(o["comparisons"][0]["historical_outcome"], None)

    def test_market_collected_after_model_not_paired(self):
        self.market["as_of_utc"] = (self.now + timedelta(minutes=1)).isoformat()
        self.assertEqual(pair(self.snapshot, self.market)["reason"], "MARKET_NOT_PRIOR_OR_TOO_OLD")

    def test_market_older_than_twelve_and_half_hours_rejected(self):
        self.market["as_of_utc"] = (self.now - timedelta(hours=13)).isoformat()
        self.assertEqual(pair(self.snapshot, self.market)["matched_count"], 0)

    def test_wrong_league_never_matches(self):
        self.price["league"] = "championship"
        self.assertEqual(pair(self.snapshot, self.market)["matched_count"], 0)

    def test_similar_but_not_same_team_rejected(self):
        self.price["home"] = "Everton Women"
        self.assertEqual(pair(self.snapshot, self.market)["matched_count"], 0)

    def test_misdated_match_rejected(self):
        self.price["kickoff_utc"] = (self.now + timedelta(days=2, hours=3)).isoformat()
        self.assertEqual(pair(self.snapshot, self.market)["matched_count"], 0)

    def test_duplicate_market_match_rejected(self):
        self.market["events"].append({**self.price, "source_event_id": "extra-id"})
        self.assertEqual(pair(self.snapshot, self.market)["exclusions"]["AMBIGUOUS_MARKET_MATCH"], 1)

    def test_invalid_probability_rejected(self):
        self.price["p_home"] = .9
        self.assertEqual(pair(self.snapshot, self.market)["matched_count"], 0)

    def test_market_last_update_later_than_snapshot_rejected(self):
        self.price["market_last_update_utc"] = (self.now + timedelta(minutes=1)).isoformat()
        self.assertEqual(pair(self.snapshot, self.market)["matched_count"], 0)

    def test_match_normalization_is_conservative(self):
        self.assertEqual(identity("Atlético"), identity("Atletico"))
        self.assertNotEqual(identity("Manchester United"), identity("Manchester City"))


if __name__ == "__main__":
    unittest.main()
