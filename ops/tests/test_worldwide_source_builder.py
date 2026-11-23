"""No-network integration tests for the actual worldwide collection pipeline."""
import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldwide_source_builder import (
    build, historical, openliga_history, sportsdb_events, market_events, OPENFOOTBALL,
    SPORTSDB, OPENLIGA, MAX_CALLS,
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

    def history_fallback_sources(self):
        """A sparse current file, audited older history and two live fixtures."""
        catalog = copy.deepcopy(self.catalog)
        catalog["cards"] = [{
            "id": "bundesliga2", "sportsdb_directory_id": "4399",
            "source_files": ["2026-27/de.2.json"],
            "coverage_state": "CURRENT_SOURCE_NO_FORECAST",
        }]
        wide = {
            "schema": "football-king-wide-free-leagues-v1",
            "status": "RESEARCH_ONLY",
            "production_recommendations": "DISABLED",
            "automatic_prediction_training": False,
            "market_odds_available": False,
            "collected_utc": self.now.isoformat(),
            "league_coverage": [{
                "league": "bundesliga2", "provider": "openfootball_json",
                "season_scope": "ARCHIVED_SEASON_ONLY",
                "access_status": "FETCHED",
                "dataset_path": "2025-26/de.2.json",
            }],
        }
        archive = copy.deepcopy(self.history)
        for row in archive["matches"]:
            row["date"] = row["date"].replace("2026-", "2025-")
        primary = copy.deepcopy(self.primary)
        primary["events"][0]["idLeague"] = "4399"
        responses = {
            "current": {"matches": copy.deepcopy(self.history["matches"][:1])},
            "archive": archive,
            "sportsdb": primary,
            "openliga": [{
                "team1": {"teamName": "Ajax"},
                "team2": {"teamName": "PSV"},
                "matchDateTimeUTC": self.kickoff.isoformat(),
                "matchIsFinished": False, "matchID": 101,
            }],
        }

        def loader(url):
            self.requests.append(url)
            if url == OPENFOOTBALL + "2026-27/de.2.json":
                response = responses["current"]
            elif url == OPENFOOTBALL + "2025-26/de.2.json":
                response = responses["archive"]
            elif url == OPENLIGA + "bl2/2026":
                response = responses["openliga"]
            elif url.startswith(SPORTSDB) or "eventsday.php?" in url:
                response = responses["sportsdb"]
            else:
                raise AssertionError("UNEXPECTED_REQUEST " + url)
            if isinstance(response, Exception):
                raise response
            return copy.deepcopy(response)

        return catalog, wide, responses, loader

    def test_sparse_current_history_uses_audited_archive_for_downstream_shadow(self):
        catalog, wide, responses, loader = self.history_fallback_sources()
        inp, status = build(catalog, None, wide=wide,
                            now=self.now, loader=loader)
        result = run_worldwide(inp, now=self.now)
        self.assertEqual(result["predictions_count"], 1)
        self.assertIn(OPENFOOTBALL + "2025-26/de.2.json", self.requests)
        self.assertEqual(status["historical_games"], 48)
        self.assertEqual(status["two_source_schedule_agreements"], 1)
        self.assertEqual(status["request_count"], 5)
        selected = status["leagues"][0]
        self.assertEqual(selected["historical_source"], "openfootball_json")
        self.assertEqual(selected["historical_source_path"], "2025-26/de.2.json")
        self.assertEqual(selected["sources_successful"].count("openfootball_json"), 1)
        self.assertEqual({row["date"] for row in inp["leagues"][0]["history"]},
                         {row["date"] for row in responses["archive"]["matches"]})
        self.assertFalse(result["model_calibrated"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_sufficient_current_history_wins_without_requesting_archive(self):
        catalog, wide, responses, loader = self.history_fallback_sources()
        responses["current"] = {"matches": copy.deepcopy(self.history["matches"][:30])}
        inp, status = build(catalog, None, wide=wide,
                            now=self.now, loader=loader)
        self.assertEqual(run_worldwide(inp, now=self.now)["predictions_count"], 1)
        self.assertNotIn(OPENFOOTBALL + "2025-26/de.2.json", self.requests)
        self.assertEqual(status["historical_games"], 30)
        self.assertEqual(status["leagues"][0]["historical_source_path"],
                         "2026-27/de.2.json")
        self.assertTrue(all(row["date"].startswith("2026-")
                            for row in inp["leagues"][0]["history"]))

    def test_unavailable_archive_or_insufficient_separate_histories_remain_hold(self):
        for archive in (OSError("SYNTHETIC_ARCHIVE_UNAVAILABLE"),
                        {"matches": self.history["matches"][:29]}):
            with self.subTest(archive_type=type(archive).__name__):
                self.requests = []
                catalog, wide, responses, loader = self.history_fallback_sources()
                responses["archive"] = archive
                inp, status = build(catalog, None, wide=wide,
                                    now=self.now, loader=loader)
                self.assertIn(OPENFOOTBALL + "2025-26/de.2.json", self.requests)
                self.assertEqual(inp["leagues"], [])
                self.assertEqual(status["leagues"][0]["reason"],
                                 "INSUFFICIENT_VERIFIABLE_PREVIOUS_DATE_RESULTS")
                self.assertIsNone(status["leagues"][0]["historical_source_path"])
                self.assertEqual(run_worldwide(inp, now=self.now)["predictions_count"], 0)

    def test_stale_or_unqualified_archive_audit_is_not_requested(self):
        for invalid in ("stale", "failed", "unsafe"):
            with self.subTest(audit=invalid):
                self.requests = []
                catalog, wide, responses, loader = self.history_fallback_sources()
                if invalid == "stale":
                    wide["collected_utc"] = (self.now - timedelta(hours=37)).isoformat()
                elif invalid == "failed":
                    wide["league_coverage"][0]["access_status"] = "HOLD"
                else:
                    wide["automatic_prediction_training"] = True
                inp, status = build(catalog, None, wide=wide,
                                    now=self.now, loader=loader)
                self.assertNotIn(OPENFOOTBALL + "2025-26/de.2.json", self.requests)
                self.assertEqual(inp["leagues"], [])
                self.assertEqual(run_worldwide(inp, now=self.now)["predictions_count"], 0)

    def test_archive_history_does_not_relax_prior_date_cutoff(self):
        catalog, wide, responses, loader = self.history_fallback_sources()
        for i, row in enumerate(responses["archive"]["matches"][29:]):
            row["date"] = (self.now + timedelta(days=i)).date().isoformat()
        inp, status = build(catalog, None, wide=wide,
                            now=self.now, loader=loader)
        self.assertIn(OPENFOOTBALL + "2025-26/de.2.json", self.requests)
        self.assertEqual(inp["leagues"], [])
        self.assertEqual(status["leagues"][0]["reason"],
                         "INSUFFICIENT_VERIFIABLE_PREVIOUS_DATE_RESULTS")
        self.assertEqual(run_worldwide(inp, now=self.now)["predictions_count"], 0)

    def test_archive_history_does_not_bypass_conflicting_fixture_times(self):
        catalog, wide, responses, loader = self.history_fallback_sources()
        responses["sportsdb"]["events"][0]["strTimestamp"] = (
            self.kickoff + timedelta(hours=2)).isoformat()
        inp, status = build(catalog, None, wide=wide,
                            now=self.now, loader=loader)
        self.assertEqual(status["historical_games"], 48)
        self.assertEqual(status["two_source_schedule_agreements"], 0)
        result = run_worldwide(inp, now=self.now)
        self.assertEqual(result["predictions_count"], 0)
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_german_history_fallback_still_runs_when_neither_file_qualifies(self):
        catalog, wide, responses, loader = self.history_fallback_sources()
        responses["archive"]["matches"] = responses["archive"]["matches"][:29]
        for i, row in enumerate(self.history["matches"][:44]):
            responses["openliga"].append({
                "team1": {"teamName": row["team1"]},
                "team2": {"teamName": row["team2"]},
                "matchDateTimeUTC": (self.now - timedelta(days=i + 1)).isoformat(),
                "matchIsFinished": True, "matchID": i + 200,
                "matchResults": [{"resultTypeID": 2,
                                  "pointsTeam1": row["score"]["ft"][0],
                                  "pointsTeam2": row["score"]["ft"][1]}],
            })
        inp, status = build(catalog, None, wide=wide,
                            now=self.now, loader=loader)
        self.assertEqual(status["historical_games"], 44)
        self.assertEqual(status["leagues"][0]["historical_source"],
                         "openligadb_results")
        self.assertEqual(status["leagues"][0]["historical_source_path"],
                         OPENLIGA + "bl2/2026")
        self.assertEqual({row["result_source"] for row in inp["leagues"][0]["history"]},
                         {"openligadb_results"})
        self.assertEqual(run_worldwide(inp, now=self.now)["predictions_count"], 1)

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

    def test_duplicated_feed_not_counted_as_independent_time_agreement(self):
        self.primary["events"].append(dict(self.primary["events"][0], idEvent="9002"))
        inp, status = build(self.catalog, self.market,
                            now=self.now, loader=self.loader)
        self.assertEqual(status["two_source_schedule_agreements"], 0)
        self.assertEqual(run_worldwide(inp, now=self.now)["predictions_count"], 0)

    def test_audited_archived_path_can_supply_old_training_history(self):
        self.catalog["cards"] = [{
            "id": "bundesliga2", "source_files": [],
            "coverage_state": "ARCHIVE_ONLY",
        }]
        wide = {
            "schema": "football-king-wide-free-leagues-v1",
            "status": "RESEARCH_ONLY",
            "production_recommendations": "DISABLED",
            "automatic_prediction_training": False,
            "market_odds_available": False,
            "collected_utc": self.now.isoformat(),
            "league_coverage": [{
                "league": "bundesliga2", "provider": "openfootball_json",
                "season_scope": "ARCHIVED_SEASON_ONLY",
                "access_status": "FETCHED",
                "dataset_path": "2025-26/de.2.json"}],
        }
        def source(url):
            self.requests.append(url)
            if url.startswith(OPENFOOTBALL):
                return self.history
            if "api.openligadb.de" in url:
                return [{
                    "team1": {"teamName": "Ajax"},
                    "team2": {"teamName": "PSV"},
                    "matchDateTimeUTC": self.kickoff.isoformat(),
                    "matchIsFinished": False,
                    "matchID": 101,
                }]
            raise AssertionError("UNEXPECTED_URL " + url)
        inp, status = build(self.catalog, None, wide=wide,
                            now=self.now, loader=source)
        self.assertEqual(status["eligible_catalogue_leagues"], 1)
        self.assertEqual(status["historical_games"], 48)
        self.assertEqual(status["source_scheduled_fixtures"], 1)
        self.assertEqual(status["two_source_schedule_agreements"], 0)
        self.assertEqual(run_worldwide(inp, now=self.now)["predictions_count"], 0)

    def test_german_lower_league_trains_only_with_finished_ft_and_day_crosscheck(self):
        teams = ["Ajax", "PSV", "Feyenoord", "Utrecht", "Twente", "AZ"]
        season_matches = []
        for i in range(44):
            ko = self.now - timedelta(days=i+1, hours=2)
            season_matches.append({
                "team1": {"teamName": teams[i % 6]},
                "team2": {"teamName": teams[(i+1) % 6]},
                "matchDateTimeUTC": ko.isoformat(),
                "matchIsFinished": True,
                "matchID": i + 10,
                "matchResults": [{
                    "resultTypeID": 2, "pointsTeam1": 1+i % 2,
                    "pointsTeam2": i % 2}],
            })
        season_matches.append({
            "team1": {"teamName": "Ajax"}, "team2": {"teamName": "PSV"},
            "matchDateTimeUTC": self.kickoff.isoformat(),
            "matchIsFinished": False, "matchID": 900,
            "matchResults": [],
        })
        self.catalog["cards"] = [{
            "id": "bundesliga2", "sportsdb_directory_id": "4399",
            "source_files": [], "coverage_state": "DISCOVERED_UNVERIFIED",
        }]
        def german_loader(url):
            self.requests.append(url)
            if "api.openligadb.de" in url:
                return season_matches
            if "eventsnextleague" in url:
                return {"events": []}
            if "eventsday" in url:
                return {"events": [{
                    "idLeague": "4399", "idEvent": "SD-100",
                    "strHomeTeam": "Ajax", "strAwayTeam": "PSV",
                    "strTimestamp": self.kickoff.isoformat(),
                    "strStatus": "Not Started",
                    "intHomeScore": None, "intAwayScore": None,
                }]}
            raise AssertionError("UNEXPECTED_URL " + url)
        inp, status = build(self.catalog, None, now=self.now,
                            loader=german_loader)
        self.assertEqual(status["two_source_schedule_agreements"], 1)
        self.assertEqual(status["historical_games"], 44)
        self.assertEqual(status["leagues"][0]["historical_source"],
                         "openligadb_results")
        self.assertEqual(status["leagues"][0]["historical_source_path"],
                         OPENLIGA + "bl2/2026")
        self.assertEqual(len(inp["leagues"]), 1)
        actual = run_worldwide(inp, now=self.now)
        self.assertEqual(actual["predictions_count"], 1)
        self.assertEqual(actual["predictions"][0]["league"], "bundesliga2")
        self.assertFalse(actual["positive_ev_verified"])
        self.assertEqual(actual["production_recommendations"], "DISABLED")

    def test_openliga_wrong_result_type_not_used_as_finished_training(self):
        game = {
            "team1": {"teamName": "Ajax"}, "team2": {"teamName": "PSV"},
            "matchDateTimeUTC": (
                self.now - timedelta(days=2)).isoformat(),
            "matchIsFinished": True, "matchID": 7,
            "matchResults": [{
                "resultTypeID": 1, "pointsTeam1": 3, "pointsTeam2": 1,
            }],
        }
        self.assertEqual(openliga_history([game], self.now), [])
        game["matchResults"][0]["resultTypeID"] = 2
        self.assertEqual(len(openliga_history([game], self.now)), 1)
        game["matchDateTimeUTC"] = (
            self.now + timedelta(days=1)).isoformat()
        self.assertEqual(openliga_history([game], self.now), [])

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
                         "INSUFFICIENT_VERIFIABLE_PREVIOUS_DATE_RESULTS")
        self.assertEqual(inp["leagues"], [])

    def test_unaudited_archive_path_is_not_requested(self):
        self.catalog["cards"][0]["source_files"] = ["../../secrets.json"]
        inp, status = build(self.catalog, self.market,
                            now=self.now, loader=self.loader)
        self.assertEqual(status["request_count"], 0)
        self.assertEqual(inp["leagues"], [])

    def test_japan_j1_is_sampled_even_with_twelve_league_daily_limit(self):
        self.catalog["cards"] = [
            dict(self.catalog["cards"][0], id="league_" + str(n),
                 sportsdb_directory_id=str(5500 + n))
            for n in range(22)
        ] + [{
            "id": "japan_j1", "sportsdb_directory_id": "4633",
            "source_files": ["2025/jp.1.json"],
            "coverage_state": "ARCHIVE_ONLY",
        }]
        inp, status = build(self.catalog, None, now=self.now,
                            loader=self.loader, max_leagues=12)
        self.assertEqual(status["requested_leagues"], 12)
        self.assertTrue(status["japan_j1_selected_for_source_audit"])
        self.assertTrue(status["japan_j1_is_not_automatically_forecast_qualified"])
        self.assertIn("japan_j1", [x["league"] for x in status["leagues"]])
        self.assertIn(OPENFOOTBALL + "2025/jp.1.json", self.requests)
        self.assertLessEqual(status["request_count"], MAX_CALLS)
        self.assertEqual(run_worldwide(inp, now=self.now)["predictions_count"], 0)

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
