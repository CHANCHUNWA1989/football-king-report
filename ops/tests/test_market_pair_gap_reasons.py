"""Research-only fixture-level market pairing gap explanations.

All fixtures/odds are synthetic. Tests never authorize an actual bet.
"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_pair import pair, publish
from market_pair_gap_reasons import diagnose


class MarketPairGapReasonsTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 1, 10, tzinfo=timezone.utc)
        self.kickoff = (self.now + timedelta(days=2)).isoformat()
        self.model = {
            "league": "epl", "home": "Everton", "away": "Arsenal",
            "event_id": "synthetic-a", "prediction_utc": self.now.isoformat(),
            "kickoff_utc": self.kickoff,
            "p_home": .3, "p_draw": .3, "p_away": .4,
            "production_recommendations": "DISABLED",
        }
        self.shadow = {
            "status": "SHADOW_ONLY", "as_of_utc": self.now.isoformat(),
            "predictions": [self.model], "production_recommendations": "DISABLED",
        }
        self.quote = {
            "league": "epl", "home": "Everton", "away": "Arsenal",
            "source_event_id": "synthetic-market-a",
            "kickoff_utc": self.kickoff,
            "market_last_update_utc": (self.now - timedelta(minutes=20)).isoformat(),
            "p_home": .35, "p_draw": .30, "p_away": .35,
        }
        self.market = {
            "status": "RESEARCH_ONLY",
            "as_of_utc": (self.now - timedelta(minutes=10)).isoformat(),
            "events": [self.quote], "production_recommendations": "DISABLED",
        }

    def get(self):
        return diagnose(self.shadow, self.market, pair(self.shadow, self.market))

    def assert_hold(self, result, reason):
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["unpaired_forecasts"], 1)
        self.assertEqual(result["paired_forecasts"], 0)
        self.assertEqual(result["reasons"], {reason: 1})
        self.assertEqual(result["fixtures"][0]["reason"], reason)
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["verified_ev"])
        self.assertFalse(result["eligible_for_model_scoring"])
        self.assertNotIn("p_home", json.dumps(result))
        self.assertNotIn("synthetic-market-a", json.dumps(result))

    def test_paired_has_no_missing_reason(self):
        result = self.get()
        self.assertEqual(result["paired_forecasts"], 1)
        self.assertEqual(result["unpaired_forecasts"], 0)
        self.assertEqual(result["reasons"], {})
        self.assertEqual(result["fixtures"], [])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_no_matching_team_in_market(self):
        self.market["events"] = [{**self.quote, "home": "Chelsea"}]
        self.assert_hold(self.get(), "NO_SAME_LEAGUE_TEAM_MARKET_EVENT")

    def test_wrong_league_is_not_matching_team(self):
        self.quote["league"] = "laliga"
        self.assert_hold(self.get(), "NO_SAME_LEAGUE_TEAM_MARKET_EVENT")

    def test_kickoff_time_mismatch_explained(self):
        self.quote["kickoff_utc"] = (self.now + timedelta(days=2, hours=2)).isoformat()
        self.assert_hold(self.get(), "MARKET_KICKOFF_MORE_THAN_45M_AWAY")

    def test_invalid_quote_age_explained(self):
        self.quote["market_last_update_utc"] = (
            self.now - timedelta(hours=9)).isoformat()
        self.assert_hold(self.get(), "QUOTE_NOT_VALID_AT_MARKET_CAPTURE")

    def test_quote_after_prediction_explained(self):
        self.quote["market_last_update_utc"] = (
            self.now + timedelta(minutes=1)).isoformat()
        self.assert_hold(self.get(), "QUOTE_NOT_VALID_AT_MARKET_CAPTURE")

    def test_non_numeric_price_probability_cannot_be_paired(self):
        self.quote["p_home"] = "0.35"
        self.assert_hold(self.get(), "NO_USABLE_MARKET_PROBABILITY")

    def test_ambiguous_two_market_events_not_silently_matched(self):
        self.market["events"].append({**self.quote, "source_event_id": "synthetic-market-b"})
        self.assertEqual(pair(self.shadow, self.market)["matched_count"], 0)
        self.assert_hold(self.get(), "AMBIGUOUS_MARKET_MATCH")

    def test_market_snapshot_after_prediction_fails_closed(self):
        self.market["as_of_utc"] = (self.now + timedelta(minutes=1)).isoformat()
        result = self.get()
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["paired_forecasts"], 0)
        self.assertEqual(result["fixtures"], [])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_invalid_forecast_does_not_become_eligible(self):
        self.model["p_home"] = True
        result = self.get()
        self.assert_hold(result, "INVALID_FORECAST_OR_TIME")

    def test_publish_separate_research_gap_artifact_without_raw_odds(self):
        with tempfile.TemporaryDirectory() as folder:
            site = Path(folder)
            (site / "shadow.json").write_text(json.dumps(self.shadow), encoding="utf-8")
            market_file = site / "market_input.json"
            self.market["events"] = [{**self.quote, "home": "Chelsea"}]
            market_file.write_text(json.dumps(self.market), encoding="utf-8")
            summary = publish(site, market_file)
            path = site / "market_pair_gap_reasons.json"
            self.assertTrue(path.is_file())
            diagnostic = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(diagnostic["reasons"],
                             {"NO_SAME_LEAGUE_TEAM_MARKET_EVENT": 1})
            self.assertEqual(summary["matched_count"], 0)
            self.assertEqual(summary["production_recommendations"], "DISABLED")
            self.assertNotIn("bookmaker", json.dumps(diagnostic).lower())


if __name__ == "__main__":
    unittest.main()
