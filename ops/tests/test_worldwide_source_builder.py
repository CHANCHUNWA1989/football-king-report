"""No-network integration tests for the actual worldwide collection pipeline."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldwide_source_builder import (
    build, historical, sportsdb_events, market_events, OPENFOOTBALL,
    SPORTSDB, MAX_CALLS,
)
from worldwide_shadow import generate as run_worldwide


class WorldwideSourceBuilderTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 10, 4, tzinfo=timezone.utc)
        self.kickoff = self.now + timedelta(days=2)
        self.catalog = {
            "schema": "football-king-global-league-catalog-v1",
            "as_of_utc": self.now.isoformat(),
            "production_recommendations": "DISABLED",
            "executable_odds_confirmed": False,
            "all_world_leagues_complete": False,
            "cards": [{
                "id": "eredivisie", "name": "Dutch Eredivisie",
                "sportsdb_directory_id": "4337",
                "source_files": ["2026-27/nl.1.json"],
                "coverage_state": "CURRENT_SOURCE_NO_FORECAST"}],
        }
        names = ["Ajax", "PSV", "Feyenoord", "AZ Alkmaar", "Utrecht", "Twente"]
        self.history = {"matches": []}
        for i in range(48):
            self.history["matches"].append({
                "team1": names[i % 6], "team2": names[(i+1) % 6],
                "date": (self.now - timedelta(days=i + 1)).date().isoformat(),
                "score": {"ft": [i % 3, (i + 1) % 3]},
            })
        self.primary = {"events": [{
            "idLeague": "4337", "strHomeTeam": "Ajax", "strAwayTeam": "PSV",
            "idEvent": "9001", "strTimestamp": self.kickoff.isoformat(),
            "strStatus": "Not Started", "intHomeScore": None, "intAwayScore": None,
        }]}
        self.market = {
            "status": "RESEARCH_ONLY", "as_of_utc": (
                self.now - timedelta(minutes=3)).isoformat(),
            "production_recommendations": "DISABLED",
            "events": [{
                "league": "eredivisie", "home": "Ajax", "away": "PSV",
                "source_event_id": "market-9",
                "kickoff_utc": self.kickoff.isoformat(),
                "market_last_update_utc": (
                    self.now - timedelta(minutes=4)).isoformat(),
                "p_home": .2, "p_draw": .3, "p_away": .5,
            }],
        }
        self.requests = []
    def loader(self, url):
        self.requests.append(url)
        if url.startswith(OPENFOOTBALL):
            return self.history
        if url.startswith(SPORTSDB):
            return self.primary
        raise AssertionError("UNEXPECTED_REQUEST " + url)

    def test_end_to_end_true_external_history_and_two_publishers(self):
        inp, status = build(self.catalog, self.market,
                            now=self.now, loader=self.loader)
        self.assertEqual(inp["production_recommendations"], "DISABLED")
        self.assertEqual(status["two_source_schedule_agreements"], 1)
        self.assertEqual(status["request_count"], 2)
        self.assertEqual(len(inp["leagues"]), 1)
        self.assertEqual(len(inp["leagues"][0]["history"]), 48)
        self.assertEqual(len(inp["leagues"][0]["fixture_observations"]), 2)
        # Market probabilities are not propagated into training/model input.
        self.assertNotIn("p_home", json.dumps(inp))
        result = run_worldwide(inp, now=self.now)
        self.assertEqual(result["predictions_count"], 1)
        self.assertEqual(result["predictions"][0]["league"], "eredivisie")
        self.assertFalse(result["model_calibrated"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_no_second_publisher_never_generates_forecast(self):
        inp, st = build(self.catalog, None, now=self.now, loader=self.loader)
        self.assertEqual(st["two_source_schedule_agreements"], 0)
        self.assertEqual(run_worldwide(inp, now=self.now)["predictions_count"], 0)

    def test_future_scores_not_used_in_training(self):
        self.history["matches"][0]["date"] = (
            self.now + timedelta(days=2)).date().isoformat()
        rows = historical(self.history, now=self.now, source_path="2026-27/nl.1.json")
        self.assertEqual(len(rows), 47)
        self.assertTrue(all(x["date"] < self.now.date().isoformat() for x in rows))

    def test_stale_market_quote_cannot_be_second_timestamp_feed(self):
        self.market["as_of_utc"] = (
            self.now - timedelta(hours=24)).isoformat()
        inp, status = build(self.catalog, self.market,
                            now=self.now, loader=self.loader)
        self.assertEqual(status["two_source_schedule_agreements"], 0)
        self.assertEqual(run_worldwide(inp, now=self.now)["predictions_count"], 0)

    def test_source_must_match_exact_league_id(self):
        self.primary["events"][0]["idLeague"] = "9999"
        inp, status = build(self.catalog, self.market,
                            now=self.now, loader=self.loader)
        self.assertEqual(status["two_source_schedule_agreements"], 0)
        self.assertEqual(run_worldwide(inp, now=self.now)["predictions_count"], 0)

    def test_stale_catalog_fails_closed_without_requests(self):
        self.catalog["as_of_utc"] = (
            self.now - timedelta(days=3)).isoformat()
        inp, status = build(self.catalog, self.market,
                            now=self.now, loader=self.loader)
        self.assertEqual(status["reason"], "CATALOG_MISSING_OR_UNSAFE")
        self.assertEqual(status["request_count"], 0)
        self.assertEqual(inp["leagues"], [])

    def test_missing_training_scores_never_produces_model(self):
        self.history["matches"] = [{
            **x, "score": {"ft": None}} for x in self.history["matches"]]
        inp, status = build(self.catalog, self.market,
                            now=self.now, loader=self.loader)
        self.assertEqual(status["reason"], "NO_QUALIFIED_WORLDWIDE_INPUT")
        self.assertEqual(status["leagues"][0]["reason"],
                         "INSUFFICIENT_OPENFOOTBALL_HISTORY")
        self.assertEqual(inp["leagues"], [])

    def test_unaudited_archive_path_is_not_requested(self):
        self.catalog["cards"][0]["source_files"] = ["../../secrets.json"]
        inp, status = build(self.catalog, self.market,
                            now=self.now, loader=self.loader)
        self.assertEqual(status["request_count"], 0)
        self.assertEqual(inp["leagues"], [])

    def test_request_budget_bounded(self):
        more = [dict(self.catalog["cards"][0], id="league_" + str(n),
                     sportsdb_directory_id=str(5500 + n))
                for n in range(30)]
        self.catalog["cards"] = more
        _, status = build(self.catalog, self.market, now=self.now,
                          loader=self.loader)
        self.assertLessEqual(status["requested_leagues"], 12)
        self.assertLessEqual(status["request_count"], MAX_CALLS)


if __name__ == "__main__":
    unittest.main()
