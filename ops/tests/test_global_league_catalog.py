"""A discovered competition is not a verified model, fixture or bet."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from global_league_catalog import build, discover_tree, publish, SCHEMA, parse_sportsdb_directory, COUNTRIES


class WorldwideCatalogTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 10, 4, tzinfo=timezone.utc)
        self.wide = {
            "schema": "football-king-global-free-league-site-v1",
            "status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
            "provider_market_odds_available": False,
            "generated_utc": self.now.isoformat(),
            "source_as_of_utc": self.now.isoformat(),
            "league_cards": [
                {"id": "eredivisie", "name": "荷甲", "provider": "openfootball_json",
                 "season_scope": "CURRENT_SEASON_FILE", "access_status": "FETCHED",
                 "records": 306},
                {"id": "league_one", "name": "英甲", "provider": "openfootball_json",
                 "season_scope": "ARCHIVED_SEASON_ONLY", "access_status": "FETCHED",
                 "records": 552},
            ]}
        self.shadow = {"schema": "football-king-uncalibrated-shadow-1",
                       "status": "SHADOW_ONLY",
                       "as_of_utc": self.now.isoformat(),
                       "production_recommendations": "DISABLED",
                       "predictions": [
                           {"league": "epl", "home": "Arsenal", "away": "Chelsea"},
                           {"league": "bundesliga", "home": "Bayern", "away": "Dortmund"}]}
        self.pairing = {"status": "RESEARCH_ONLY",
                        "production_recommendations": "DISABLED",
                        "comparisons": [{"league": "epl"}]}

    def test_global_country_request_budget_bounded(self):
        self.assertEqual(len(COUNTRIES), len(set(COUNTRIES)))
        self.assertGreaterEqual(len(COUNTRIES), 25)
        self.assertLessEqual(len(COUNTRIES), 28)
        self.assertIn("Japan", COUNTRIES)
        self.assertIn("South Africa", COUNTRIES)

    def test_latest_source_tree_discovers_current_files_only(self):
        tree = {"truncated": False, "tree": [
            {"type": "blob", "path": "2026-27/en.1.json"},
            {"type": "blob", "path": "2026-27/nl.1.json"},
            {"type": "blob", "path": "2026-27/jp.1.json"},
            {"type": "blob", "path": "2026-27/at.cup.json"},
            {"type": "blob", "path": "2025-26/de.2.json"},
            {"type": "blob", "path": "2026-27/../../malicious.json"},
            {"type": "tree", "path": "2026-27/ar.1.json"},
            {"type": "blob", "path": "2026-27/random.bin"}]}
        found = discover_tree(tree, now=self.now)
        self.assertEqual({row["id"] for row in found},
                         {"epl", "eredivisie", "japan_j1", "openfootball_at_cup"})
        self.assertEqual(len(found), 4)

    def test_no_unverified_discovery_promotes_prediction(self):
        extra = [{"id": "openfootball_jp_1", "name": "OpenFootball JP.1",
                  "path": "2026-27/jp.1.json",
                  "discovery": "PUBLIC_SOURCE_FILENAME_ONLY"}]
        result = build(self.wide, self.shadow, self.pairing,
                       now=self.now, discovered=extra)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertFalse(result["all_world_leagues_complete"])
        self.assertFalse(result["executable_odds_confirmed"])
        byid = {row["id"]: row for row in result["cards"]}
        self.assertEqual(byid["epl"]["coverage_state"], "UNCALIBRATED_SHADOW")
        self.assertEqual(byid["epl"]["paired_research_cases"], 1)
        self.assertEqual(byid["eredivisie"]["coverage_state"],
                         "CURRENT_SOURCE_NO_FORECAST")
        self.assertEqual(byid["league_one"]["coverage_state"], "ARCHIVE_ONLY")
        self.assertEqual(byid["openfootball_jp_1"]["coverage_state"],
                         "DISCOVERED_UNVERIFIED")
        self.assertEqual(byid["openfootball_jp_1"]["shadow_predictions"], 0)
        self.assertTrue(all(x["production_recommendations"] == "DISABLED"
                            and x["executable_odds"] is False
                            and x["forecast_validated"] is False
                            for x in result["cards"]))

    def test_new_league_shadow_is_onboarded_without_betting_claims(self):
        worldwide = {
            "schema": "football-king-worldwide-uncalibrated-shadow-v1",
            "status": "SHADOW_ONLY", "as_of_utc": self.now.isoformat(),
            "production_recommendations": "DISABLED",
            "model_calibrated": False, "positive_ev_verified": False,
            "predictions": [
                {"league": "japan_j1",
                 "worldwide_two_distinct_schedule_feeds": True,
                 "production_recommendations": "DISABLED"},
                {"league": "fake_unverified",
                 "worldwide_two_distinct_schedule_feeds": False,
                 "production_recommendations": "DISABLED"},
            ]}
        result = build(self.wide, self.shadow, self.pairing, now=self.now,
                       worldwide=worldwide)
        byid = {row["id"]: row for row in result["cards"]}
        self.assertEqual(byid["japan_j1"]["shadow_predictions"], 1)
        self.assertEqual(byid["japan_j1"]["worldwide_shadow_predictions"], 1)
        self.assertEqual(byid["japan_j1"]["coverage_state"], "UNCALIBRATED_SHADOW")
        self.assertNotIn("fake_unverified", byid)
        self.assertFalse(byid["japan_j1"]["forecast_validated"])
        self.assertFalse(byid["japan_j1"]["executable_odds"])

    def test_free_country_directory_can_add_leagues_but_not_predictions(self):
        doc = {"countries": [
            {"idLeague": "4570", "strLeague": "EFL Cup", "strSport": "Soccer"},
            {"idLeague": "4330", "strLeague": "Scottish Premier League",
             "strSport": "Soccer"},
            {"idLeague": "9010", "strLeague": "Basketball", "strSport": "Basketball"},
            {"idLeague": "1234", "strLeague": "<script>evil</script>",
             "strSport": "Soccer"},
        ]}
        rows = parse_sportsdb_directory(doc, "Scotland")
        self.assertEqual(len(rows), 3)
        known = next(x for x in rows if x["sportsdb_league_id"] == "4330")
        self.assertEqual(known["id"], "scottish_premiership")
        output = build(self.wide, self.shadow, self.pairing,
                       now=self.now, sportsdb=rows)
        mapping = {x["id"]: x for x in output["cards"]}
        self.assertEqual(mapping["sportsdb_4570"]["coverage_state"],
                         "DISCOVERED_UNVERIFIED")
        self.assertFalse(mapping["sportsdb_4570"]["forecast_validated"])
        self.assertEqual(mapping["sportsdb_4570"]["shadow_predictions"], 0)
        self.assertFalse(mapping["sportsdb_4570"]["executable_odds"])
        self.assertFalse(output["all_world_leagues_complete"])

    def test_invalid_sportsdb_ids_and_non_soccer_are_excluded(self):
        sample = {"countries": [
            {"idLeague": "../bad", "strLeague": "Bad", "strSport": "Soccer"},
            {"idLeague": "1234", "strLeague": "Not football", "strSport": "Basketball"},
            {"idLeague": "3211", "strLeague": "Wrong Country",
             "strSport": "Soccer", "strCountry": "Brazil"},
            {"idLeague": "4328", "strLeague": "English Premier League",
             "strSport": "Soccer"},
        ]}
        found = parse_sportsdb_directory(sample, "England")
        self.assertEqual([x["id"] for x in found], ["epl"])

    def test_exact_lower_division_provider_aliases_do_not_create_duplicate_leagues(self):
        cases = [
            ("Germany", "German 2. Bundesliga", "bundesliga2"),
            ("Germany", "Germany Liga 3", "germany_liga3"),
            ("England", "English League 1", "league_one"),
            ("England", "English League 2", "league_two"),
            ("Italy", "Italian Serie B", "serie_b"),
            ("France", "French Ligue 2", "ligue2"),
            ("Brazil", "Brazilian Brasileirao", "brazil_serie_a"),
            ("USA", "American Major League Soccer", "usa_mls"),
        ]
        for country, league, expected in cases:
            with self.subTest(country=country, league=league):
                data = {"countries": [{
                    "idLeague": "4399", "strLeague": league,
                    "strSport": "Soccer", "strCountry": country,
                }]}
                observed = parse_sportsdb_directory(data, country)
                self.assertEqual(len(observed), 1)
                self.assertEqual(observed[0]["id"], expected)

    def test_curated_league_directory_ids_available_without_country_top_ten(self):
        result = build(self.wide, self.shadow, self.pairing, now=self.now)
        byid = {x["id"]: x for x in result["cards"]}
        for league, expected in (
            ("bundesliga2", "4399"), ("germany_liga3", "4639"),
            ("japan_j1", "4633"), ("league_one", "4396"),
            ("league_two", "4397"), ("eredivisie", "4337"),
            ("usa_mls", "4346")
        ):
            with self.subTest(league=league):
                self.assertEqual(byid[league]["sportsdb_directory_id"], expected)
                self.assertFalse(byid[league]["forecast_validated"])
                self.assertFalse(byid[league]["executable_odds"])

    def test_dynamic_conflict_blocks_false_league_identity(self):
        result = build(
            self.wide, self.shadow, self.pairing, now=self.now,
            sportsdb=[{
                "id": "bundesliga2", "sportsdb_league_id": "99999",
                "name": "Wrong German League",
                "discovery": "PUBLIC_THE_SPORTS_DB_LEAGUE_ID_ONLY",
            }])
        card = next(x for x in result["cards"] if x["id"] == "bundesliga2")
        self.assertTrue(card["sportsdb_id_conflict"])
        self.assertNotIn("sportsdb_directory_id", card)
        self.assertEqual(card["shadow_predictions"], 0)

    def test_stale_snapshots_not_counted_as_current(self):
        self.wide["source_as_of_utc"] = (
            self.now - timedelta(hours=40)).isoformat()
        self.shadow["as_of_utc"] = (
            self.now - timedelta(hours=40)).isoformat()
        result = build(self.wide, self.shadow, self.pairing, now=self.now)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["leagues_with_shadow"], 0)
        byid = {row["id"]: row for row in result["cards"]}
        self.assertEqual(byid["eredivisie"]["coverage_state"], "DISCOVERED_UNVERIFIED")
        self.assertFalse(byid["eredivisie"]["current_source_confirmed"])
        self.assertEqual(byid["eredivisie"]["shadow_predictions"], 0)

    def test_bad_source_claim_cannot_mark_current(self):
        self.wide["provider_market_odds_available"] = True
        result = build(self.wide, self.shadow, self.pairing, now=self.now)
        byid = {row["id"]: row for row in result["cards"]}
        self.assertFalse(byid["eredivisie"]["current_source_confirmed"])

    def test_malformed_or_truncated_tree_rejected(self):
        self.assertEqual(discover_tree({"truncated": True, "tree": []},
                                       now=self.now), [])
        self.assertEqual(discover_tree({"truncated": False, "tree": {}},
                                       now=self.now), [])

    def test_offline_catalog_always_publishes_even_without_feeds(self):
        with tempfile.TemporaryDirectory() as temp:
            out = publish(temp, discover=False)
            self.assertEqual(out["status"], "HOLD")
            self.assertGreaterEqual(out["catalogued_leagues"], 25)
            saved = json.loads(
                (Path(temp) / "global_league_catalog.json").read_text())
            self.assertEqual(saved["production_recommendations"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
