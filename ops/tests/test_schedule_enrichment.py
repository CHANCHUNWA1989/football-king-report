"""Six-league UTC enrichment uses only two independent fixture timestamps."""
import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from schedule_enrichment import enrich
from shadow_forecast import generate


class SafeScheduleEnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 10, 0, tzinfo=timezone.utc)
        self.ko = self.now + timedelta(days=2, hours=12)
        self.rows = []
        teams = ["Arsenal FC", "Chelsea FC", "Liverpool FC",
                 "Everton FC", "Fulham FC", "Aston Villa FC"]
        for i in range(48):
            self.rows.append({
                "date": (self.now - timedelta(days=i + 1)).date().isoformat(),
                "home": teams[i % 6], "away": teams[(i + 1) % 6],
                "score_ft": [1 + (i % 2), i % 2],
                "status": "FINISHED", "kickoff_utc": None,
            })
        self.rows.append({"date": self.ko.astimezone(
            timezone(timedelta(hours=8))).date().isoformat(),
            "home": "Arsenal FC", "away": "Chelsea FC",
            "status": "SCHEDULED", "score_ft": None,
            "event_id": "original-gateway-fixture", "kickoff_utc": None})
        self.audit = {
            "schema": "football-king-extra-source-audit-v1",
            "status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
            "collected_utc": self.now.isoformat(),
            "providers": [{"provider": "thesportsdb", "status": "PARTIAL_COVERAGE",
                           "sampled_fixture_count": 1}],
            "sampled_fixtures": [{"league": "epl", "home": "Arsenal",
                                   "away": "Chelsea", "provider": "thesportsdb",
                                   "provider_event_id": "sportsdb-1",
                                   "kickoff_utc": self.ko.isoformat(),
                                   "status": "SCHEDULED", "score_ft": None}]}
        self.market = {
            "status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
            "as_of_utc": (self.now - timedelta(minutes=10)).isoformat(),
            "events": [{"league": "epl", "home": "Arsenal FC",
                        "away": "Chelsea", "source_event_id": "market-1",
                        "kickoff_utc": self.ko.isoformat(),
                        "market_last_update_utc": (self.now - timedelta(minutes=12)).isoformat(),
                        "p_home": .1, "p_draw": .1, "p_away": .8}]}

    def test_safe_two_source_utc_allows_original_fixture_only(self):
        result, info = enrich(self.rows, "epl", self.audit, self.market, self.now)
        self.assertEqual(info["updated_existing_schedules"], 1)
        self.assertEqual(result[-1]["kickoff_utc"], self.ko.isoformat())
        self.assertIsNone(self.rows[-1]["kickoff_utc"])
        self.assertFalse(info["market_probabilities_used_as_model_input"])
        self.assertFalse(info["price_inputs_used"])
        self.assertEqual(result[0], self.rows[0])

    def test_forecast_uses_original_history_and_extra_schedule_only(self):
        def gateway(season, league, clock):
            if league != "epl":
                return {"status": "HOLD", "matches": []}
            return {"status": "READY_RESEARCH", "matches": copy.deepcopy(self.rows)}
        result = generate(now=self.now, getter=gateway,
                          secondary_snapshot=self.audit,
                          market_schedule=self.market)
        self.assertEqual(result["predictions_count"], 1)
        self.assertEqual(result["additional_precise_schedule_utc"], 1)
        case = result["predictions"][0]
        self.assertEqual(case["schedule_utc_source"], "thesportsdb")
        self.assertEqual(case["training_games"], 48)
        self.assertFalse(case["calibrated"])
        self.assertEqual(case["production_recommendations"], "DISABLED")

    def test_secondary_single_source_cannot_enrich(self):
        self.market["events"] = []
        res, info = enrich(self.rows, "epl", self.audit, self.market, self.now)
        self.assertEqual(info["updated_existing_schedules"], 0)
        self.assertIsNone(res[-1]["kickoff_utc"])

    def test_disagreement_and_wrong_day_fail_closed(self):
        self.market["events"][0]["kickoff_utc"] = (
            self.ko + timedelta(hours=2)).isoformat()
        self.assertEqual(enrich(self.rows, "epl", self.audit, self.market,
                                self.now)[1]["updated_existing_schedules"], 0)
        self.market["events"][0]["kickoff_utc"] = self.ko.isoformat()
        self.rows[-1]["date"] = (self.ko.date() - timedelta(days=2)).isoformat()
        self.assertEqual(enrich(self.rows, "epl", self.audit, self.market,
                                self.now)[1]["updated_existing_schedules"], 0)

    def test_stale_or_future_snapshot_fail_closed(self):
        self.audit["collected_utc"] = (
            self.now - timedelta(hours=17)).isoformat()
        self.assertEqual(enrich(self.rows, "epl", self.audit, self.market,
                                self.now)[1]["updated_existing_schedules"], 0)
        self.audit["collected_utc"] = self.now.isoformat()
        self.market["as_of_utc"] = (
            self.now + timedelta(minutes=12)).isoformat()
        self.assertEqual(enrich(self.rows, "epl", self.audit, self.market,
                                self.now)[1]["updated_existing_schedules"], 0)

    def test_cannot_invent_fixture_or_change_finished_result(self):
        result, info = enrich(self.rows[:-1], "epl", self.audit, self.market, self.now)
        self.assertEqual(len(result), len(self.rows) - 1)
        self.assertEqual(info["updated_existing_schedules"], 0)

    def test_conflicting_original_precise_time_is_not_overridden(self):
        self.rows[-1]["kickoff_utc"] = (
            self.ko + timedelta(hours=3)).isoformat()
        res, info = enrich(self.rows, "epl", self.audit, self.market, self.now)
        self.assertEqual(info["updated_existing_schedules"], 0)
        self.assertEqual(res[-1]["kickoff_utc"], self.rows[-1]["kickoff_utc"])

    def test_wrong_league_fails_closed(self):
        res, info = enrich(self.rows, "seriea", self.audit, self.market, self.now)
        self.assertEqual(info["updated_existing_schedules"], 0)
        self.assertEqual(res, self.rows)

    def test_duplicate_market_fixture_is_ambiguous(self):
        self.market["events"].append(dict(self.market["events"][0]))
        self.assertEqual(enrich(self.rows, "epl", self.audit, self.market,
                                self.now)[1]["updated_existing_schedules"], 0)


if __name__ == "__main__":
    unittest.main()
