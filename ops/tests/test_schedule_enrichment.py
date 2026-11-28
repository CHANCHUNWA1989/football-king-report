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

    def test_two_sources_restore_missing_fixture_without_changing_history(self):
        history_only = self.rows[:-1]
        result, info = enrich(history_only, "epl", self.audit, self.market, self.now)
        self.assertEqual(len(result), len(history_only) + 1)
        self.assertEqual(info["added_crosschecked_schedules"], 1)
        self.assertEqual(result[:-1], history_only)
        self.assertEqual(result[-1]["status"], "SCHEDULED")
        self.assertEqual(result[-1]["score_ft"], None)
        self.assertEqual(result[-1]["kickoff_utc"], self.ko.isoformat())
        self.assertTrue(result[-1]["added_from_two_time_agreeing_fixtures"])

    def test_missing_fixture_is_not_added_from_single_source(self):
        self.market["events"] = []
        result, info = enrich(self.rows[:-1], "epl", self.audit, self.market, self.now)
        self.assertEqual(len(result), len(self.rows) - 1)
        self.assertEqual(info["added_crosschecked_schedules"], 0)

    def test_unknown_history_team_cannot_be_invented(self):
        self.audit["sampled_fixtures"][0]["home"] = "Totally Unknown Club"
        self.market["events"][0]["home"] = "Totally Unknown Club"
        result, info = enrich(self.rows[:-1], "epl", self.audit, self.market, self.now)
        self.assertEqual(info["added_crosschecked_schedules"], 0)
        self.assertEqual(result, self.rows[:-1])

    def test_restored_external_fixture_feeds_forecast_without_external_scores(self):
        def gateway(season, league, clock):
            if league != "epl":
                return {"status": "HOLD", "matches": []}
            return {"status": "READY_RESEARCH", "matches": copy.deepcopy(self.rows[:-1])}
        result = generate(now=self.now, getter=gateway,
                          secondary_snapshot=self.audit,
                          market_schedule=self.market)
        self.assertEqual(result["predictions_count"], 1)
        self.assertEqual(result["additional_precise_schedule_utc"], 1)
        case = result["predictions"][0]
        self.assertEqual(case["schedule_utc_source"], "thesportsdb")
        self.assertEqual(case["training_games"], 48)
        self.assertEqual(case["production_recommendations"], "DISABLED")

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


    def test_cross_midnight_utc_date_normalized_before_forecast(self):
        # 17:15 UTC on Oct 12 is 01:15 Hong Kong on Oct 13.
        # The gateway date may be the UTC calendar day, whereas forecasts
        # require the Hong Kong calendar day after two-source UTC confirmation.
        ko = self.now + timedelta(days=2, hours=17, minutes=15)
        self.rows[-1]["date"] = ko.date().isoformat()
        self.audit["sampled_fixtures"][0]["kickoff_utc"] = ko.isoformat()
        self.market["events"][0]["kickoff_utc"] = ko.isoformat()
        updated, info = enrich(self.rows, "epl", self.audit, self.market, self.now)
        self.assertEqual(info["updated_existing_schedules"], 1)
        self.assertEqual(updated[-1]["date"], "2026-10-13")
        self.assertEqual(updated[-1]["kickoff_utc"], ko.isoformat())
        self.assertEqual(self.rows[-1]["date"], "2026-10-12")
        self.assertIsNone(self.rows[-1]["kickoff_utc"])

        def gateway(season, league, clock):
            return ({"status": "READY_RESEARCH", "matches": copy.deepcopy(self.rows)}
                    if league == "epl" else {"status": "HOLD", "matches": []})

        forecast = generate(now=self.now, getter=gateway,
                            secondary_snapshot=self.audit,
                            market_schedule=self.market)
        self.assertEqual(forecast["predictions_count"], 1)
        case = forecast["predictions"][0]
        self.assertEqual(case["kickoff_utc"], ko.isoformat())
        self.assertEqual(case["training_games"], 48)
        self.assertEqual(case["training_cutoff_local_day"], "2026-10-09")
        self.assertEqual(case["production_recommendations"], "DISABLED")

    def test_cross_midnight_single_source_cannot_normalize_or_predict(self):
        ko = self.now + timedelta(days=2, hours=17, minutes=15)
        self.rows[-1]["date"] = ko.date().isoformat()
        self.audit["sampled_fixtures"][0]["kickoff_utc"] = ko.isoformat()
        self.market["events"] = []
        updated, info = enrich(self.rows, "epl", self.audit, self.market, self.now)
        self.assertEqual(info["updated_existing_schedules"], 0)
        self.assertEqual(updated[-1]["date"], ko.date().isoformat())
        self.assertIsNone(updated[-1]["kickoff_utc"])

        def gateway(season, league, clock):
            return ({"status": "READY_RESEARCH", "matches": copy.deepcopy(self.rows)}
                    if league == "epl" else {"status": "HOLD", "matches": []})

        forecast = generate(now=self.now, getter=gateway,
                            secondary_snapshot=self.audit,
                            market_schedule=self.market)
        self.assertEqual(forecast["predictions_count"], 0)
        self.assertEqual(forecast["production_recommendations"], "DISABLED")



    def add_second_provider(self, offset_minutes=0):
        self.audit["providers"].append({
            "provider": "football_data_org", "status": "PARTIAL_COVERAGE",
            "sampled_fixture_count": 1})
        other = dict(self.audit["sampled_fixtures"][0],
                     provider="football_data_org", provider_event_id="fd-1",
                     kickoff_utc=(self.ko + timedelta(minutes=offset_minutes)).isoformat())
        self.audit["sampled_fixtures"].append(other)

    def test_new_provider_agreement_does_not_suppress_forecast(self):
        self.add_second_provider()
        result, info = enrich(self.rows, "epl", self.audit, self.market, self.now)
        self.assertEqual(info["updated_existing_schedules"], 1)
        self.assertEqual(info["source_time_agreements"], 1)
        self.assertEqual(result[-1]["kickoff_utc"], self.ko.isoformat())
        self.assertEqual(result[-1]["schedule_utc_source"], "thesportsdb")
        self.assertEqual(result[:-1], self.rows[:-1])
        self.audit["sampled_fixtures"].reverse()
        self.assertEqual(enrich(self.rows, "epl", self.audit, self.market, self.now)[0], result)

        def gateway(season, league, clock):
            return ({"status": "READY_RESEARCH", "matches": copy.deepcopy(self.rows)}
                    if league == "epl" else {"status": "HOLD", "matches": []})
        report = generate(now=self.now, getter=gateway,
                          secondary_snapshot=self.audit, market_schedule=self.market)
        self.assertEqual(report["predictions_count"], 1)
        self.assertEqual(report["predictions"][0]["training_games"], 48)
        self.assertFalse(report["predictions"][0]["calibrated"])
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_two_providers_restore_once_without_changing_history(self):
        self.add_second_provider()
        result, info = enrich(self.rows[:-1], "epl", self.audit, self.market, self.now)
        self.assertEqual(info["added_crosschecked_schedules"], 1)
        self.assertEqual(result[:-1], self.rows[:-1])
        self.assertIsNone(result[-1]["score_ft"])

    def test_two_providers_disagree_even_when_each_close_to_market(self):
        self.audit["sampled_fixtures"][0]["kickoff_utc"] = (
            self.ko - timedelta(minutes=40)).isoformat()
        self.add_second_provider(40)
        result, info = enrich(self.rows, "epl", self.audit, self.market, self.now)
        self.assertEqual(info["source_time_agreements"], 0)
        self.assertEqual(result, self.rows)

    def test_duplicate_provider_veto_even_with_other_agreement(self):
        self.add_second_provider()
        self.audit["sampled_fixtures"].append(dict(self.audit["sampled_fixtures"][0]))
        result, info = enrich(self.rows, "epl", self.audit, self.market, self.now)
        self.assertEqual(info["source_time_agreements"], 0)
        self.assertEqual(result, self.rows)

    def test_multiple_providers_do_not_bypass_market_freshness(self):
        self.add_second_provider()
        self.market["as_of_utc"] = (self.now - timedelta(hours=17)).isoformat()
        result, info = enrich(self.rows, "epl", self.audit, self.market, self.now)
        self.assertEqual(info["source_time_agreements"], 0)
        self.assertEqual(result, self.rows)


    def complete_secondary_archive(self):
        # Build the full sanitized source contract; no real keys or quotes.
        leagues = ("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1")
        names = ("thesportsdb", "api_football", "football_data_org", "sportmonks")
        self.add_second_provider()
        records = self.audit["sampled_fixtures"]
        providers = []
        for name in names:
            counts = {league: sum(r["provider"] == name and r["league"] == league
                                  for r in records) for league in leagues}
            count = sum(counts.values())
            providers.append({
                "provider": name, "configured": bool(count),
                "status": "PARTIAL" if count else "NOT_CONFIGURED",
                "production_recommendations": "DISABLED",
                "can_replace_1x2_market": False,
                "original_bookmaker_odds_redistributed": False,
                "league_result_verification_complete": False,
                "calls_attempted": int(bool(count)),
                "counts_by_league": counts, "sampled_fixture_count": count})
        self.audit.update(
            providers=providers,
            started_utc=(self.now-timedelta(minutes=2)).isoformat(),
            six_league_independent_results_verified=False,
            odds_fallback_confirmed=False, coverage_is_complete=False,
            original_api_payload_redistributed=False)

    def test_valid_two_publisher_archive_recovers_shadow_without_market(self):
        self.complete_secondary_archive()
        self.market["as_of_utc"] = (self.now - timedelta(days=8)).isoformat()
        for market in (self.market, None):
            result, info = enrich(self.rows, "epl", self.audit, market, self.now)
            self.assertEqual(info["secondary_only_time_agreements"], 1)
            self.assertEqual(info["source_time_agreements"], 0)
            self.assertFalse(info["market_schedule_eligible"])
            self.assertEqual(info["updated_existing_schedules"], 1)
            self.assertEqual(result[-1]["kickoff_utc"], self.ko.isoformat())
            self.assertEqual(result[-1]["schedule_utc_source"],
                             "secondary_only:football_data_org+thesportsdb")
            self.assertEqual(result[:-1], self.rows[:-1])

            def gateway(season, league, clock):
                return ({"status": "READY_RESEARCH", "matches": copy.deepcopy(self.rows)}
                        if league == "epl" else {"status": "HOLD", "matches": []})
            report = generate(now=self.now, getter=gateway,
                              secondary_snapshot=self.audit, market_schedule=market)
            self.assertEqual(report["predictions_count"], 1)
            self.assertEqual(report["independent_schedule_market_time_agreements"], 0)
            self.assertEqual(report["sources"][0]["secondary_only_fixture_utc_agreements"], 1)
            self.assertEqual(report["predictions"][0]["training_games"], 48)
            self.assertFalse(report["market_odds_available"])
            self.assertFalse(report["predictions"][0]["calibrated"])
            self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_secondary_only_requires_exact_time_and_valid_archive(self):
        self.complete_secondary_archive()
        original = copy.deepcopy(self.audit)
        self.audit["sampled_fixtures"][1]["kickoff_utc"] = (
            self.ko + timedelta(minutes=1)).isoformat()
        self.assertEqual(enrich(self.rows, "epl", self.audit, None, self.now)[0], self.rows)
        self.audit = copy.deepcopy(original)
        self.audit["providers"][2]["sampled_fixture_count"] += 1
        self.assertEqual(enrich(self.rows, "epl", self.audit, None, self.now)[0], self.rows)
        self.audit = original
        self.audit["collected_utc"] = (self.now + timedelta(minutes=1)).isoformat()
        self.assertEqual(enrich(self.rows, "epl", self.audit, None, self.now)[0], self.rows)

    def test_secondary_only_cannot_bypass_fresh_market_conflict(self):
        self.complete_secondary_archive()
        self.market["events"][0]["kickoff_utc"] = (
            self.ko + timedelta(hours=2)).isoformat()
        result, info = enrich(self.rows, "epl", self.audit, self.market, self.now)
        self.assertEqual(result, self.rows)
        self.assertEqual(info["secondary_only_time_agreements"], 0)
        self.assertEqual(info["source_time_agreements"], 0)


if __name__ == "__main__":
    unittest.main()
