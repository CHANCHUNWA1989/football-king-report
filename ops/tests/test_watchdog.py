"""Regression tests for independent published-site monitor."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from watchdog import evaluate, evaluate_research_layers, evaluate_market_layer, evaluate_qualification_layers, evaluate_recommendations_layer, evaluate_optional_provider_layer, evaluate_global_free_leagues


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 9, 4, tzinfo=timezone.utc)
        self.checked = (self.now - timedelta(hours=2)).isoformat()
        self.state = {"checked_utc": self.checked, "status": "RESEARCH_ONLY",
                      "quality_status": "RESEARCH_ONLY",
                      "production_recommendations": "DISABLED"}
        self.quality = {"checked_utc": self.checked, "status": "RESEARCH_ONLY",
                        "critical_errors": []}

    def test_fresh_research_publication_ok(self):
        self.assertTrue(evaluate(self.state, self.quality, now=self.now)["ok"])

    def test_stale_publication_alerts(self):
        self.state["checked_utc"] = self.quality["checked_utc"] = (
            self.now - timedelta(hours=13)).isoformat()
        self.assertIn("PUBLISHED_REPORT_STALE_OR_FUTURE",
                      evaluate(self.state, self.quality, now=self.now)["failures"])

    def test_hold_reports_source_alert(self):
        self.state["status"] = "HOLD"
        self.state["quality_status"] = self.quality["status"] = "HOLD"
        self.assertIn("PUBLIC_SOURCE_HOLD",
                      evaluate(self.state, self.quality, now=self.now)["failures"])

    def test_recommendation_safety_alert(self):
        self.state["production_recommendations"] = "ENABLED"
        self.assertIn("UNSAFE_RECOMMENDATIONS_ENABLED",
                      evaluate(self.state, self.quality, now=self.now)["failures"])

    def test_research_layers_require_hold_for_market_evidence(self):
        self.assertFalse(evaluate_research_layers(
            {"status": "INCONCLUSIVE", "all_leagues_verified": False,
             "production_recommendations": "DISABLED"},
            {"model_calibrated": False, "market_odds_available": False,
             "production_recommendations": "DISABLED", "predictions": [], "predictions_count": 0},
            {"status": "HOLD", "production_recommendations": "DISABLED"}))

    def test_improper_betting_status_fails_watchdog(self):
        errors = evaluate_research_layers(
            {"status": "PARTIAL_CHECK", "all_leagues_verified": False,
             "production_recommendations": "DISABLED"},
            {"model_calibrated": True, "market_odds_available": False,
             "production_recommendations": "DISABLED", "predictions": [], "predictions_count": 0},
            {"status": "HOLD", "production_recommendations": "DISABLED"})
        self.assertIn("INVALID_SHADOW_RESEARCH_PROVENANCE", errors)

    def test_shadow_count_mismatch_alerts(self):
        errors = evaluate_research_layers(
            {"status": "INCONCLUSIVE", "all_leagues_verified": False,
             "production_recommendations": "DISABLED"},
            {"model_calibrated": False, "market_odds_available": False,
             "production_recommendations": "DISABLED", "predictions": [], "predictions_count": 8},
            {"status": "HOLD", "production_recommendations": "DISABLED"})
        self.assertIn("SHADOW_COUNT_MISMATCH", errors)


    def test_current_market_layer_is_valid(self):
        sample={"status": "RESEARCH_ONLY", "source_state": "RESEARCH_ONLY",
                "market_as_of_utc": (self.now - timedelta(minutes=15)).isoformat(),
                "model_events": 27, "market_events": 120, "matched_count": 7,
                "production_recommendations": "DISABLED"}
        pairs={"status":"RESEARCH_ONLY", "matched_count":7,
               "comparisons": [{} for _ in range(7)],
               "production_recommendations":"DISABLED"}
        self.assertFalse(evaluate_market_layer(sample,pairs,now=self.now))

    def test_market_stale_after_day_alerts(self):
        sample={"status":"HOLD", "source_state":"RESEARCH_ONLY",
                "market_as_of_utc": (self.now - timedelta(hours=27)).isoformat(),
                "model_events": 27, "market_events": 120, "matched_count": 0,
                "production_recommendations":"DISABLED"}
        pairs={"status":"HOLD", "matched_count":0, "comparisons":[],
               "production_recommendations":"DISABLED"}
        self.assertIn("DERIVED_MARKET_DATA_STALE",
                      evaluate_market_layer(sample,pairs,now=self.now))

    def test_market_count_mismatch_alerts(self):
        sample={"status":"RESEARCH_ONLY", "source_state":"HOLD", "model_events":1,
                "market_events":2, "matched_count":3,
                "production_recommendations":"DISABLED"}
        pairs={"status":"RESEARCH_ONLY", "matched_count":3, "comparisons":[{}, {}, {}],
               "production_recommendations":"DISABLED"}
        self.assertIn("MARKET_MATCH_COUNT_IMPOSSIBLE",
                      evaluate_market_layer(sample,pairs,now=self.now))


    def test_all_qualification_layers_safe(self):
        center={"production_recommendations":"DISABLED",
                "six_league_result_verification_complete":False,
                "total_shadow_candidates":27,
                "total_completed_comparable_samples":0,
                "total_strict_market_pairs":13}
        coverage={"league_coverage":[{"league":x} for x in
                     ("epl","championship","bundesliga","laliga","seriea","ligue1")],
                  "results_independently_verified_all_leagues":False,
                  "production_recommendations":"DISABLED"}
        ab={"promotion_allowed":False,"production_recommendations":"DISABLED",
            "candidate_count":27}
        gate={"status":"HOLD","automated_release_supported":False,
              "model_promoted":False,"production_recommendations":"DISABLED",
              "settled_samples":0}
        market={"matched_count":13}
        self.assertFalse(evaluate_qualification_layers(center,coverage,ab,gate,market))
        ab["promotion_allowed"]=True
        self.assertIn("UNSAFE_AB_PROMOTION_OR_COUNT",
                      evaluate_qualification_layers(center,coverage,ab,gate,market))

    def test_recommender_watchdog_refuses_orphaned_or_betting_eligible_picks(self):
        pairs={"matched_count":1,"comparisons":[{"case_id":"match-1"}]}
        suggestion={"schema":"football-king-explainable-research-selections-v1",
                    "selection_mode":"SHADOW_RESEARCH_ONLY",
                    "production_recommendations":"DISABLED",
                    "automatic_bets":False,"model_is_uncalibrated":True,
                    "market_prices_are_not_executable":True,
                    "validated_positive_expected_value":False,
                    "selected_count":1,"paired_count":1,
                    "fallback_mode":"NOT_NEEDED",
                    "model_only_count":0,"model_only_watchlist":[],
                    "model_only_is_betting_advice":False,
                    "selections":[{"case_id":"match-1","production_recommendations":"DISABLED",
                                   "executable_market_odds_available":False,
                                   "value_bet_verified":False,"suggested_stake":None,
                                   "reliability":"UNCALIBRATED_RESEARCH_ONLY"}],
                    "reviews":[]}
        self.assertFalse(evaluate_recommendations_layer(suggestion,pairs))
        suggestion["selections"][0]["case_id"]="invented"
        self.assertIn("UNPAIRED_OR_DUPLICATE_SELECTION",
                      evaluate_recommendations_layer(suggestion,pairs))
        suggestion["selections"][0]["case_id"]="match-1"
        suggestion["selections"][0]["suggested_stake"]=100
        self.assertIn("UNSAFE_SELECTION_CONTENT",
                      evaluate_recommendations_layer(suggestion,pairs))

    def test_optional_sources_safe_without_three_keys(self):
        data={"schema":"football-king-source-overlay-v1",
              "status":"RESEARCH_ONLY","production_recommendations":"DISABLED",
              "can_replace_market_1x2":False,
              "independently_verified_six_league_results":False,
              "source_samples_used_as_forecast_training":False,
              "matched_kickoff_agreements":0,
              "kickoff_disagreements_needing_review":0,
              "providers":[{"provider":p} for p in
                    ("thesportsdb","api_football","football_data_org","sportmonks")]}
        self.assertFalse(evaluate_optional_provider_layer(data))
        data["can_replace_market_1x2"]=True
        self.assertIn("UNSAFE_OPTIONAL_FOOTBALL_SOURCE",
                      evaluate_optional_provider_layer(data))

    def test_global_free_no_key_feed_keeps_research_status_only(self):
        rows=[{"provider":"openfootball_json",
               "season_scope":"ARCHIVED_SEASON_ONLY",
               "access_status":"NOT_YET_COLLECTED",
               "precise_utc_kickoffs_confirmed":0} for _ in range(27)]
        rows += [{"provider":"openligadb",
                  "season_scope":"OPENLIGA_2026_SEASON_UNCONFIRMED",
                  "access_status":"NOT_YET_COLLECTED"} for _ in range(3)]
        wide={"schema":"football-king-global-free-league-site-v1",
              "status":"HOLD",
              "provider_names":["openfootball_json","openligadb"],
              "source_count":2,"league_file_total":30,
              "league_cards":rows,"successful_league_files":0,
              "provider_market_odds_available":False,
              "training_evidence_validated":False,
              "historic_data_can_be_presented_as_live":False,
              "production_recommendations":"DISABLED"}
        self.assertEqual(evaluate_global_free_leagues(wide),[])
        wide["provider_market_odds_available"]=True
        self.assertIn("MISLEADING_GLOBAL_LEAGUE_COVERAGE",evaluate_global_free_leagues(wide))
        wide["provider_market_odds_available"]=False
        wide["league_cards"][0]["precise_utc_kickoffs_confirmed"]=15
        self.assertIn("UNVERIFIED_OPENFOOTBALL_TIMEZONE",evaluate_global_free_leagues(wide))

if __name__ == "__main__":
    unittest.main()
