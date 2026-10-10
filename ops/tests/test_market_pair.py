"""Strict same-fixture, strictly earlier market snapshot; never infer from aliases."""
import sys
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_pair import pair, identity, publish


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

    def test_corrupt_market_cache_publishes_safe_hold(self):
        with tempfile.TemporaryDirectory() as folder:
            site = Path(folder)
            (site / "shadow.json").write_text(json.dumps(self.snapshot), encoding="utf-8")
            bad_cache = site / "market.json"
            bad_cache.write_text("{partial-json", encoding="utf-8")
            result = publish(site, bad_cache)
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(result["matched_count"], 0)
            self.assertEqual(result["source_state"], "HOLD")
            self.assertEqual(result["production_recommendations"], "DISABLED")
            self.assertTrue((site / "market_comparison.json").exists())

    def test_non_object_market_cache_cannot_crash_or_pair(self):
        with tempfile.TemporaryDirectory() as folder:
            site = Path(folder)
            (site / "shadow.json").write_text(json.dumps(self.snapshot), encoding="utf-8")
            bad_cache = site / "market.json"
            bad_cache.write_text("[]", encoding="utf-8")
            result = publish(site, bad_cache)
            self.assertEqual(result["matched_count"], 0)
            self.assertEqual(result["source_state"], "HOLD")

    def test_invalid_market_payload_never_raises(self):
        result = pair(self.snapshot, None)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["matched_count"], 0)

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

    def test_quote_collected_after_actual_row_forecast_is_excluded(self):
        # The batch as_of can be 2 minutes after a single forecast row.
        # Comparing a later market update with that row would leak future data.
        earlier = self.now - timedelta(minutes=1)
        self.forecast["prediction_utc"] = earlier.isoformat()
        self.market["as_of_utc"] = (self.now - timedelta(seconds=15)).isoformat()
        self.price["market_last_update_utc"] = (self.now - timedelta(seconds=30)).isoformat()
        self.assertEqual(pair(self.snapshot, self.market)["matched_count"], 0)

    def test_duplicate_model_cannot_reuse_one_market_event(self):
        self.snapshot["predictions"].append({
            **self.forecast, "event_id": "another-source-record"})
        result = pair(self.snapshot, self.market)
        self.assertEqual(result["matched_count"], 1)
        self.assertEqual(result["exclusions"]["MARKET_ALREADY_PAIRED"], 1)

    def test_match_normalization_is_conservative(self):
        self.assertEqual(identity("Atlético"), identity("Atletico"))
        self.assertNotEqual(identity("Manchester United"), identity("Manchester City"))


    def test_malformed_matching_quote_cannot_poison_valid_market_pair(self):
        self.market["events"].insert(0, {
            **self.price, "source_event_id": "broken-utc",
            "kickoff_utc": "not-a-date"})
        result = pair(self.snapshot, self.market)
        self.assertEqual(result["matched_count"], 1)
        self.assertEqual(result["comparisons"][0]["market_event_id"], "soccer-key-1")

    def test_malformed_quote_update_time_skipped(self):
        self.market["events"].insert(0, {
            **self.price, "source_event_id": "broken-update",
            "market_last_update_utc": None})
        self.assertEqual(pair(self.snapshot, self.market)["matched_count"], 1)

    def test_blank_or_identical_forecast_teams_fail_closed(self):
        self.forecast["home"] = None
        self.assertEqual(pair(self.snapshot, self.market)["matched_count"], 0)
        self.forecast["home"] = "Arsenal"
        self.assertEqual(pair(self.snapshot, self.market)["matched_count"], 0)

    def test_index_does_not_turn_multiple_valid_quotes_into_one(self):
        self.market["events"].append({**self.price, "source_event_id": "second-valid-quote"})
        matched=pair(self.snapshot,self.market)
        self.assertEqual(matched["matched_count"], 0)
        self.assertEqual(matched["exclusions"].get("AMBIGUOUS_MARKET_MATCH"),1)

if __name__ == "__main__":
    unittest.main()
