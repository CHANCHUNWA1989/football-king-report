"""Curated 2026/27 Serie A source-name joins; all fixtures here are synthetic.

The official OpenFootball 2026/27 it.1 dataset uses Frosinone Calcio,
Cagliari Calcio and Venezia FC, while the two independently timestamped
fixture metadata sources use the short names. No sportsbook prices/FT evidence
or betting admission are created in this test.
"""
import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from team_identity import team_id, same_team, alias_index
from schedule_enrichment import enrich
from shadow_forecast import generate


class SerieACuratedAliasScheduleTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 1, 8, tzinfo=timezone.utc)
        self.ko = datetime(2026, 11, 1, 14, tzinfo=timezone.utc)
        self.history = []
        clubs = ("Frosinone Calcio", "Torino FC", "SS Lazio",
                 "Cagliari Calcio", "Venezia FC", "Como 1907",
                 "US Lecce", "Genoa CFC")
        for i in range(48):
            self.history.append({
                "date": (self.now - timedelta(days=i + 1)).date().isoformat(),
                "home": clubs[i % 8], "away": clubs[(i + 1) % 8],
                "score_ft": [i % 3, (i + 1) % 3],
                "status": "FINISHED", "kickoff_utc": None,
            })
        self.audit = {
            "schema": "football-king-extra-source-audit-v1",
            "status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
            "collected_utc": (self.now - timedelta(minutes=30)).isoformat(),
            "providers": [{"provider": "thesportsdb", "status": "PARTIAL",
                           "sampled_fixture_count": 2}],
            "sampled_fixtures": [
                {"league": "seriea", "home": "Frosinone", "away": "Torino",
                 "provider": "thesportsdb", "provider_event_id": "synthetic-1",
                 "kickoff_utc": self.ko.isoformat(), "status": "SCHEDULED",
                 "score_ft": None},
                {"league": "seriea", "home": "Lazio", "away": "Cagliari",
                 "provider": "thesportsdb", "provider_event_id": "synthetic-2",
                 "kickoff_utc": self.ko.isoformat(), "status": "SCHEDULED",
                 "score_ft": None},
            ],
        }
        self.market = {
            "status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
            "as_of_utc": (self.now - timedelta(minutes=90)).isoformat(),
            "events": [
                {"league": "seriea", "home": "Frosinone", "away": "Torino",
                 "source_event_id": "synthetic-quote-1", "kickoff_utc": self.ko.isoformat(),
                 "market_last_update_utc": (self.now - timedelta(hours=2)).isoformat(),
                 "p_home": .35, "p_draw": .30, "p_away": .35},
                {"league": "seriea", "home": "Lazio", "away": "Cagliari",
                 "source_event_id": "synthetic-quote-2", "kickoff_utc": self.ko.isoformat(),
                 "market_last_update_utc": (self.now - timedelta(hours=2)).isoformat(),
                 "p_home": .45, "p_draw": .25, "p_away": .30},
            ],
        }

    def test_verified_seriea_long_short_club_names_match_only_this_league(self):
        cases = (("Frosinone Calcio", "Frosinone"),
                 ("Cagliari Calcio", "Cagliari"),
                 ("Venezia FC", "Venezia"))
        for long_name, short_name in cases:
            with self.subTest(team=long_name):
                self.assertTrue(same_team("seriea", long_name, short_name))
                self.assertEqual(team_id("seriea", long_name),
                                 team_id("seriea", short_name))
                self.assertFalse(same_team("epl", long_name, short_name))
        self.assertFalse(same_team("seriea", "Venezia FC", "Venezia Women"))
        self.assertFalse(same_team("seriea", "Frosinone", "Frosinone U19"))
        self.assertFalse(same_team("seriea", "Cagliari", "Cagliari Primavera"))
        self.assertNotEqual(team_id("seriea", "Frosinone"),
                            team_id("seriea", "Cagliari"))
        self.assertIn("seriea", alias_index())

    def test_matching_time_sources_can_restore_two_missing_schedules(self):
        original = copy.deepcopy(self.history)
        upgraded, diag = enrich(self.history, "seriea", self.audit,
                                self.market, self.now)
        self.assertEqual(upgraded[:len(original)], original)
        self.assertEqual(self.history, original)
        self.assertEqual(diag["source_time_agreements"], 2)
        self.assertEqual(diag["added_crosschecked_schedules"], 2)
        self.assertEqual(len(upgraded), len(original) + 2)
        self.assertEqual({(r["home"], r["away"]) for r in upgraded[-2:]},
                         {("Frosinone Calcio", "Torino FC"),
                          ("SS Lazio", "Cagliari Calcio")})
        for row in upgraded[-2:]:
            self.assertEqual(row["kickoff_utc"], self.ko.isoformat())
            self.assertEqual(row["date"], "2026-11-01")
            self.assertIsNone(row["score_ft"])
            self.assertEqual(row["status"], "SCHEDULED")
            self.assertTrue(row["schedule_independent_time_agreement_only"])
            self.assertEqual(row["production_recommendations"], "DISABLED")

    def test_research_model_produces_forecasts_without_modified_training(self):
        original = copy.deepcopy(self.history)

        def gateway(season, league, clock):
            if league == "seriea":
                return {"status": "READY_RESEARCH", "matches": copy.deepcopy(self.history)}
            return {"status": "HOLD", "matches": []}

        report = generate(now=self.now, getter=gateway,
                          secondary_snapshot=self.audit, market_schedule=self.market)
        self.assertEqual(self.history, original)
        self.assertEqual(report["predictions_count"], 2)
        self.assertEqual(report["additional_precise_schedule_utc"], 2)
        self.assertEqual({(x["home"], x["away"]) for x in report["predictions"]},
                         {("Frosinone Calcio", "Torino FC"),
                          ("SS Lazio", "Cagliari Calcio")})
        self.assertTrue(all(x["training_games"] == 48 and
                            x["training_cutoff_local_day"] == "2026-10-31" and
                            not x["calibrated"] and
                            x["production_recommendations"] == "DISABLED"
                            for x in report["predictions"]))
        self.assertFalse(report["model_calibrated"])
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_missing_second_source_cannot_create_a_fixture(self):
        self.market["events"] = []
        upgraded, diag = enrich(self.history, "seriea", self.audit,
                                self.market, self.now)
        self.assertEqual(upgraded, self.history)
        self.assertEqual(diag["added_crosschecked_schedules"], 0)

    def test_conflicting_kickoff_stays_unmatched(self):
        self.market["events"][0]["kickoff_utc"] = (
            self.ko + timedelta(hours=2)).isoformat()
        upgraded, diag = enrich(self.history, "seriea", self.audit,
                                self.market, self.now)
        self.assertEqual(diag["added_crosschecked_schedules"], 1)
        self.assertEqual(len(upgraded), len(self.history) + 1)
        self.assertEqual((upgraded[-1]["home"], upgraded[-1]["away"]),
                         ("SS Lazio", "Cagliari Calcio"))

    def test_unknown_or_youth_team_cannot_join(self):
        self.audit["sampled_fixtures"][0]["home"] = "Frosinone U19"
        self.market["events"][0]["home"] = "Frosinone U19"
        upgraded, diag = enrich(self.history, "seriea", self.audit,
                                self.market, self.now)
        self.assertEqual(diag["added_crosschecked_schedules"], 1)
        self.assertEqual((upgraded[-1]["home"], upgraded[-1]["away"]),
                         ("SS Lazio", "Cagliari Calcio"))


if __name__ == "__main__":
    unittest.main()
