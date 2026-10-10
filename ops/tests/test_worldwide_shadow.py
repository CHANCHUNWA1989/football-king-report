"""Any league can enter isolated Shadow Mode only after strict source checks."""
import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from worldwide_shadow import generate, publish


class WorldwideShadowTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 10, 4, tzinfo=timezone.utc)
        self.kickoff = self.now + timedelta(days=2)
        self.history = []
        teams = ["Team A", "Team B", "Team C", "Team D", "Team E", "Team F"]
        for i in range(48):
            self.history.append({
                "home": teams[i % 6], "away": teams[(i + 1) % 6],
                "date": (self.now - timedelta(days=i + 1)).date().isoformat(),
                "status": "FINISHED", "score_ft": [1 + i % 2, i % 2],
                "result_source": "openfootball_json"})
        upcoming = {
            "home": "Team A", "away": "Team B",
            "kickoff_utc": self.kickoff.isoformat(),
            "captured_utc": self.now.isoformat(),
            "status": "SCHEDULED", "score_ft": None,
        }
        self.doc = {
            "schema": "football-king-worldwide-candidate-input-v1",
            "collected_utc": self.now.isoformat(),
            "production_recommendations": "DISABLED",
            "leagues": [{
                "id": "japan_j1", "history": self.history,
                "fixture_observations": [
                    {**upcoming, "provider": "thesportsdb",
                     "provider_event_id": "TS-1"},
                    {**upcoming, "provider": "football_data_org",
                     "provider_event_id": "FD-1"}]}]}

    def test_new_unlisted_league_model_trains_without_betting_status(self):
        out = generate(self.doc, now=self.now)
        self.assertEqual(out["status"], "SHADOW_ONLY")
        self.assertEqual(out["predictions_count"], 1)
        self.assertEqual(out["predictions"][0]["league"], "japan_j1")
        self.assertEqual(out["predictions"][0]["training_games"], 48)
        self.assertFalse(out["predictions"][0]["calibrated"])
        self.assertFalse(out["predictions"][0]["fixture_timestamp_independently_attested"])
        self.assertFalse(out["market_odds_available"])
        self.assertFalse(out["positive_ev_verified"])
        self.assertEqual(out["production_recommendations"], "DISABLED")

    def test_one_source_cannot_unlock_any_prediction(self):
        self.doc["leagues"][0]["fixture_observations"].pop()
        self.assertEqual(generate(self.doc, now=self.now)["predictions_count"], 0)

    def test_two_sources_with_different_kickoff_rejected(self):
        self.doc["leagues"][0]["fixture_observations"][1]["kickoff_utc"] = (
            self.kickoff + timedelta(minutes=15)).isoformat()
        self.assertEqual(generate(self.doc, now=self.now)["predictions_count"], 0)

    def test_stale_capture_rejected(self):
        self.doc["leagues"][0]["fixture_observations"][1]["captured_utc"] = (
            self.now - timedelta(hours=18)).isoformat()
        self.assertEqual(generate(self.doc, now=self.now)["predictions_count"], 0)

    def test_future_or_same_day_score_not_training(self):
        self.doc["leagues"][0]["history"] = [
            {**x, "date": self.now.date().isoformat()} for x in self.history]
        self.assertEqual(generate(self.doc, now=self.now)["predictions_count"], 0)

    def test_raw_price_field_is_not_allowed(self):
        self.doc["leagues"][0]["fixture_observations"][1]["decimal_odds"] = 999
        self.assertEqual(generate(self.doc, now=self.now)["predictions_count"], 0)

    def test_duplicate_fixture_feed_cannot_fake_independence(self):
        self.doc["leagues"][0]["fixture_observations"][1]["provider"] = "thesportsdb"
        self.assertEqual(generate(self.doc, now=self.now)["predictions_count"], 0)

    def test_unknown_world_league_id_malformed_ignored(self):
        self.doc["leagues"][0]["id"] = "../secrets"
        self.assertEqual(generate(self.doc, now=self.now)["predictions_count"], 0)

    def test_duplicate_league_blocks_do_not_double_predictions(self):
        self.doc["leagues"].append(copy.deepcopy(self.doc["leagues"][0]))
        self.assertEqual(generate(self.doc, now=self.now)["predictions_count"], 0)

    def test_missing_input_always_emits_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = publish(tmp, str(Path(tmp) / "absent.json"))
            self.assertEqual(out["status"], "HOLD")
            payload = json.loads((Path(tmp) / "worldwide_shadow.json").read_text())
            self.assertFalse(payload["model_calibrated"])
            self.assertEqual(payload["production_recommendations"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
