"""Fail-closed publication security and ten-hour freshness policy tests."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release_guard import finalize


class PublicationGuardTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 9, 4, tzinfo=timezone.utc)
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.site = Path(self.root.name)
        self.stamp = (self.now - timedelta(hours=2)).isoformat()
        self.report = {"checked_utc": self.stamp, "status": "RESEARCH_ONLY",
                       "production_recommendations": "DISABLED"}
        self.status = {"checked_utc": self.stamp, "status": "RESEARCH_ONLY",
                       "quality_status": "RESEARCH_ONLY", "production_recommendations": "DISABLED"}
        self.quality = {"checked_utc": self.stamp, "status": "RESEARCH_ONLY",
                        "critical_errors": [], "public_matches": 6,
                        "matches_with_precise_kickoff": 1,
                        "production_recommendations": "DISABLED"}
        self.validation = {"status": "HOLD", "n": 0, "reason": "NO_VERIFIED_EVIDENCE",
                           "production_recommendations": "DISABLED"}
        self.shadow = {"status": "HOLD", "as_of_utc": self.stamp, "predictions_count": 0,
                       "predictions": [], "market_odds_available": False,
                       "model_calibrated": False, "production_recommendations": "DISABLED"}
        self.crosscheck = {"status": "INCONCLUSIVE", "all_leagues_verified": False,
                           "score_conflicts": 0, "score_comparisons": 0,
                           "matched_identical_home_away": 0,
                           "production_recommendations": "DISABLED"}
        self.market_status = {"status": "HOLD", "reason": "NO_VALID_DATA",
                              "matched_count": 0, "source_state": "HOLD",
                              "market_events": 0,
                              "production_recommendations": "DISABLED"}
        self.market_pairs = {"status": "HOLD", "matched_count": 0,
                             "production_recommendations": "DISABLED"}
        self.coverage={"production_recommendations":"DISABLED",
                       "results_independently_verified_all_leagues":False,
                       "league_coverage":[{"league":code} for code in
                         ("epl","championship","bundesliga","laliga","seriea","ligue1")],
                       "total_confirmed_kickoffs":0}
        self.ab={"status":"HOLD","promotion_allowed":False,
                 "candidate_count":0,"production_recommendations":"DISABLED"}
        self.center={"production_recommendations":"DISABLED",
                     "six_league_result_verification_complete":False,
                     "total_completed_comparable_samples":0,
                     "total_strict_market_pairs":0}
        self.gate={"status":"HOLD","automated_release_supported":False,
                   "model_promoted":False,"settled_samples":0,
                   "failed_conditions":["insufficient_samples"],
                   "production_recommendations":"DISABLED"}
        self.validation["forward_archive_samples"]=0
        self.selections={"schema":"football-king-explainable-research-selections-v1",
                         "status":"RESEARCH_ONLY",
                         "selection_mode":"SHADOW_RESEARCH_ONLY",
                         "production_recommendations":"DISABLED",
                         "automatic_bets":False,
                         "validated_positive_expected_value":False,
                         "model_is_uncalibrated":True,
                         "market_prices_are_not_executable":True,
                         "estimated_roi":None,
                         "paired_count":0,
                         "selected_count":0,"selections":[],"reviews":[],
                         "fallback_mode":"NOT_NEEDED",
                         "model_only_is_betting_advice":False,
                         "model_only_count":0,"model_only_watchlist":[]}
        self.integrity={
            "schema":"football-king-fixture-integrity-v1",
            "status":"HOLD", "production_recommendations":"DISABLED",
            "blocked_from_research_recommendations":True,
            "never_used_to_rewrite_frozen_forecasts":True,
            "no_independent_result_verification_claim":True,
            "conflicting_kickoff_observations":0,
            "disagreements":[]
        }
        self.extra={"schema":"football-king-source-overlay-v1",
                    "production_recommendations":"DISABLED",
                    "status":"HOLD",
                    "source_samples_used_as_forecast_training":False,
                    "independently_verified_six_league_results":False,
                    "can_replace_market_1x2":False,
                    "providers":[{"provider":p} for p in
                        ("thesportsdb","api_football","football_data_org","sportmonks")]}
        self.extensions={
            "schema":"football-king-free-research-extension-site-v1",
            "status":"HOLD",
            "production_recommendations":"DISABLED",
            "historical_data_only_cannot_validate_current_season":True,
            "no_paid_or_unlicensed_1x2_quotes":True,
            "used_to_promote_model":False,
            "providers":[{"provider":"openfootapi","status":"NOT_YET_COLLECTED"},
                         {"provider":"statsbomb_open_data","status":"NOT_YET_COLLECTED"}]}
        self.wide={"schema":"football-king-global-free-league-site-v1",
                   "status":"HOLD","production_recommendations":"DISABLED",
                   "provider_market_odds_available":False,
                   "training_evidence_validated":False,
                   "historic_data_can_be_presented_as_live":False,
                   "source_count":2,
                   "provider_names":["openfootball_json","openligadb"],
                   "backup_policy":"PRECISE_OPENLIGA_UTC_SCHEDULE_ONLY",
                   "backup_scheduled_fixtures":[],
                   "league_file_total":30,
                   "league_cards":[
                       {"provider":"openfootball_json",
                        "access_status":"NOT_YET_COLLECTED"} for _ in range(27)] +
                       [{"provider":"openligadb",
                         "access_status":"NOT_YET_COLLECTED"} for _ in range(3)]}
        self.weather={
            "schema":"football-king-research-weather-overlay-v1",
            "status":"HOLD","production_recommendations":"DISABLED",
            "source_is_city_centre_not_venue":True,"match_venue_confirmed":False,
            "included_as_predictive_model_feature":False,
            "weather_impact_on_win_probability_validated":False,
            "market_odds_source":False,
            "data_license":"https://creativecommons.org/licenses/by/4.0/",
            "forecasts":[]
        }
        self.bsd={
            "schema":"football-king-bsd-optional-market-overlay-v1",
            "status":"HOLD","production_recommendations":"DISABLED",
            "source_licence_verified_for_derived_research":True,
            "automatic_replacement_of_main_market":False,
            "market_is_executable":False,
            "real_money_recommendations":False,
            "compared_to_primary_model":False,
            "time_valid_shadow_pairs":0,"market_event_count":0
        }
        self.write()

    def write(self):
        for filename, payload in (("report.json", self.report), ("status.json", self.status),
                                  ("quality.json", self.quality), ("validation.json", self.validation),
                                  ("shadow.json", self.shadow), ("crosscheck.json", self.crosscheck),
                                  ("market_status.json", self.market_status),
                                  ("market_comparison.json", self.market_pairs),
                                  ("league_coverage.json", self.coverage),
                                  ("ab_status.json", self.ab),
                                  ("research_center.json", self.center),
                                  ("production_gate.json", self.gate),
                                  ("research_selections.json", self.selections),
                                  ("extra_sources.json", self.extra),
                                  ("fixture_integrity.json", self.integrity),
                                  ("free_research_extensions.json", self.extensions),
                                  ("wide_leagues.json", self.wide),
                                  ("weather_context.json", self.weather),
                                  ("bsd_backup.json", self.bsd)):
            (self.site / filename).write_text(json.dumps(payload), encoding="utf-8")
        (self.site / "index.html").write_text(
            '<html><body><div class="status" id="research-banner" data-checked="' +
            self.stamp + '">OLD</div><div>正式投注推薦：停用</div>' +
            '<section id="fk-hub"><div id="fk-recommendations"><div id="fk-picks"></div></div>' +
            '<div id="fk-model-only-section"><div id="fk-model-only-list"></div></div></section>' +
            '<section id="fk-extra-sources"></section>' +
            '<section id="fk-fixture-integrity"></section>' +
            '<section id="fk-research-extensions"></section>' +
            '<section id="fk-wide-sources"></section>' +
            '<section id="fk-met-weather"></section>' +
            '<section id="fk-bsd-backup"></section>' +
            '<link rel="stylesheet" href="research_hub.css">' +
            '<script src="research_hub.js" defer></script>' +
            '<script src="freshness.js" defer></script></body></html>', encoding="utf-8")
        (self.site / "research_hub.js").write_text("'use strict';", encoding="utf-8")
        (self.site / "research_hub.css").write_text("#fk-hub{}", encoding="utf-8")

    def test_replaces_client_freshness_to_ten_hours(self):
        self.assertEqual(finalize(self.site, now=self.now)["status"], "RESEARCH_ONLY")
        js = (self.site / "freshness.js").read_text()
        self.assertIn("10*60*60*1000", js)
        h = (self.site / "index.html").read_text()
        self.assertIn('id="quality-audit"', h)
        self.assertIn('id="shadow-validation"', h)
        self.assertIn('id="shadow-research-only"', h)
        self.assertIn('id="independent-source-check"', h)
        self.assertIn('id="free-market-research"', h)
        self.assertIn('id="research-qualification"', h)
        self.assertIn('id="fk-hub"', h)
        self.assertIn('id="fk-extra-sources"', h)
        self.assertIn('id="fk-recommendations"', h)
        self.assertIn("RESEARCH_ONLY", h)

    def test_market_pair_count_mismatch_fails_closed(self):
        self.market_status["matched_count"] = 8
        self.write()
        with self.assertRaisesRegex(ValueError, "INVALID_FREE_MARKET_RESEARCH_LAYER"):
            finalize(self.site, now=self.now)

    def test_market_status_never_authorizes_production(self):
        self.market_status["production_recommendations"] = "ENABLED"
        self.write()
        with self.assertRaisesRegex(ValueError, "INVALID_FREE_MARKET_RESEARCH_LAYER"):
            finalize(self.site, now=self.now)

    def test_iphone_background_tab_refreshes_staleness_without_reload(self):
        finalize(self.site, now=self.now)
        js = (self.site / "freshness.js").read_text(encoding="utf-8")
        self.assertIn("setInterval(checkFreshness", js)
        self.assertIn("visibilitychange", js)
        self.assertIn("pageshow", js)
        html = (self.site / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="no-js-freshness-warning"', html)

    def test_stale_data_visible_hold(self):
        self.stamp = (self.now - timedelta(hours=11)).isoformat()
        self.report["checked_utc"] = self.status["checked_utc"] = self.quality["checked_utc"] = self.stamp
        self.shadow["as_of_utc"] = self.stamp
        self.write()
        self.assertEqual(finalize(self.site, now=self.now)["status"], "HOLD")
        self.assertIn("HOLD：品質或更新時間未通過", (self.site / "index.html").read_text())

    def test_bad_html_without_banner_fails_closed(self):
        content=(self.site / "index.html").read_text(encoding="utf-8")
        start=content.index('<div class="status" id="research-banner"')
        end=content.index('</div>',start)+len('</div>')
        (self.site / "index.html").write_text(content[:start]+content[end:])
        with self.assertRaisesRegex(ValueError, "MISSING_VISIBLE_SAFETY_BANNER"):
            finalize(self.site, now=self.now)

    def test_bad_model_authorization_fails_closed(self):
        self.validation["status"] = "PASS"
        self.write()
        with self.assertRaisesRegex(ValueError, "SHADOW_EVIDENCE_CANNOT_AUTHORIZE_PRODUCTION"):
            finalize(self.site, now=self.now)

    def test_missing_quality_timestamp_fails_closed(self):
        self.quality["checked_utc"] = "2026-10-08T00:00:00+00:00"
        self.write()
        with self.assertRaisesRegex(ValueError, "INCONSISTENT_CAPTURE_TIMES"):
            finalize(self.site, now=self.now)

    def test_missing_body_end_fails_closed(self):
        p=self.site / "index.html"
        p.write_text(p.read_text(encoding="utf-8").replace("</body>",""),encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "MISSING_HTML_BODY_END"):
            finalize(self.site, now=self.now)

    def test_dashboard_missing_fails_closed(self):
        p=self.site / "index.html"
        p.write_text(p.read_text(encoding="utf-8").replace('id="fk-hub"','id="not-hub"'),encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"MISSING_MOBILE_RESEARCH_DASHBOARD"):
            finalize(self.site,now=self.now)

    def test_recommender_cannot_enable_live_betting(self):
        self.selections["production_recommendations"]="ENABLED"
        self.write()
        with self.assertRaisesRegex(ValueError,"INVALID_RESEARCH_RECOMMENDATIONS"):
            finalize(self.site,now=self.now)

    def test_recommender_lying_about_executable_odds_is_rejected(self):
        self.selections["market_prices_are_not_executable"]=False
        self.write()
        with self.assertRaisesRegex(ValueError,"INVALID_RESEARCH_RECOMMENDATIONS"):
            finalize(self.site,now=self.now)

    def test_missing_recommendation_section_blocks_publication(self):
        page=self.site / "index.html"
        page.write_text(page.read_text(encoding="utf-8").replace('id="fk-recommendations"','id="missing"'))
        with self.assertRaisesRegex(ValueError,"MISSING_VISIBLE_RESEARCH_RECOMMENDATIONS"):
            finalize(self.site,now=self.now)

    def test_pure_model_fallback_cannot_claim_betting_value(self):
        self.selections["fallback_mode"]="MODEL_ONLY_LOW_EVIDENCE"
        self.selections["model_only_count"]=1
        self.selections["model_only_watchlist"]=[{
            "event_id":"shadow-100","league":"bundesliga",
            "home":"Home","away":"Away","kickoff_utc":self.stamp,
            "production_recommendations":"DISABLED",
            "reliability":"LOW_UNVALIDATED_NO_MARKET",
            "market_confirmed":False,"qualifies_for_betting":False,
            "executable_market_odds_available":False,
            "value_bet_verified":False,"suggested_stake":None}]
        self.write()
        self.assertEqual(finalize(self.site,now=self.now)["status"],"RESEARCH_ONLY")
        self.selections["model_only_watchlist"][0]["qualifies_for_betting"]=True
        self.write()
        with self.assertRaisesRegex(ValueError,"UNSAFE_MODEL_ONLY_FALLBACK_ITEM"):
            finalize(self.site,now=self.now)

    def test_pure_model_fallback_section_must_be_visible(self):
        page=self.site/"index.html"
        page.write_text(page.read_text(encoding="utf-8").replace(
            'id="fk-model-only-section"','id="absent-model-fallback"'))
        with self.assertRaisesRegex(ValueError,"MISSING_VISIBLE_FALLBACK_DISCLOSURE"):
            finalize(self.site,now=self.now)

    def test_global_small_league_backup_cannot_claim_betting_confirmation(self):
        self.wide["backup_scheduled_fixtures"]=[{
            "source":"openligadb","backup_for_schedule_only":True,
            "market_confirmed":True,"betting_recommendation":False,
            "production_recommendations":"DISABLED"}]
        self.write()
        with self.assertRaisesRegex(ValueError,"UNSAFE_GLOBAL_BACKUP_FIXTURES"):
            finalize(self.site,now=self.now)

    def test_global_archived_records_cannot_claim_live_odds(self):
        self.wide["historic_data_can_be_presented_as_live"]=True
        self.write()
        with self.assertRaisesRegex(ValueError,"UNSAFE_OR_MISSING_GLOBAL_FREE_LEAGUES"):
            finalize(self.site,now=self.now)

    def test_global_sources_section_cannot_be_hidden(self):
        html_path=self.site/"index.html"
        html_path.write_text(html_path.read_text(encoding="utf-8").replace(
            'id="fk-wide-sources"','id="missing-global-sources"'),encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"UNSAFE_OR_MISSING_GLOBAL_FREE_LEAGUES"):
            finalize(self.site,now=self.now)

    def test_bsd_backup_cannot_promote_betting(self):
        self.bsd["automatic_replacement_of_main_market"]=True
        self.write()
        with self.assertRaisesRegex(ValueError,"INVALID_BSD_FREE_MARKET_BACKUP"):
            finalize(self.site,now=self.now)

    def test_bsd_backup_section_must_be_visible(self):
        page=self.site/"index.html"
        page.write_text(page.read_text(encoding="utf-8").replace(
            'id="fk-bsd-backup"','id="missing-bsd-backup"'))
        with self.assertRaisesRegex(ValueError,"INVALID_BSD_FREE_MARKET_BACKUP"):
            finalize(self.site,now=self.now)

    def test_optional_weather_cannot_alter_predicted_win_probability(self):
        self.weather["included_as_predictive_model_feature"]=True
        self.write()
        with self.assertRaisesRegex(ValueError,"INVALID_MET_WEATHER_RESEARCH_PROVENANCE"):
            finalize(self.site,now=self.now)

    def test_weather_cannot_claim_stadium_observation(self):
        self.weather["match_venue_confirmed"]=True
        self.write()
        with self.assertRaisesRegex(ValueError,"INVALID_MET_WEATHER_RESEARCH_PROVENANCE"):
            finalize(self.site,now=self.now)

    def test_missing_weather_licence_notice_prevents_publication(self):
        p=self.site/"index.html"
        p.write_text(p.read_text(encoding="utf-8").replace(
            'id="fk-met-weather"','id="removed-weather-attribution"'),encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"INVALID_MET_WEATHER_RESEARCH_PROVENANCE"):
            finalize(self.site,now=self.now)

    def test_secondary_sources_cannot_be_promoted_to_betting(self):
        self.extra["can_replace_market_1x2"]=True
        self.write()
        with self.assertRaisesRegex(ValueError,"INVALID_ADDITIONAL_FREE_SOURCE_PROVENANCE"):
            finalize(self.site,now=self.now)

    def test_secondary_source_section_must_be_visible(self):
        p=self.site/"index.html"
        p.write_text(p.read_text(encoding="utf-8").replace(
            'id="fk-extra-sources"','id="missing-extra-sources"'),encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"INVALID_ADDITIONAL_FREE_SOURCE_PROVENANCE"):
            finalize(self.site,now=self.now)

    def test_research_extensions_cannot_become_live_xg_or_betting(self):
        self.extensions["used_to_promote_model"]=True
        self.write()
        with self.assertRaisesRegex(ValueError,"INVALID_FREE_RESEARCH_EXTENSION_PROVENANCE"):
            finalize(self.site,now=self.now)

    def test_research_extension_panel_must_be_visible(self):
        p=self.site/"index.html"
        p.write_text(p.read_text(encoding="utf-8").replace(
            'id="fk-research-extensions"','id="removed-extensions"'),encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"INVALID_FREE_RESEARCH_EXTENSION_PROVENANCE"):
            finalize(self.site,now=self.now)

    def test_cross_publisher_conflicts_must_be_disclosed(self):
        self.integrity["blocked_from_research_recommendations"]=False
        self.write()
        with self.assertRaisesRegex(ValueError,"INVALID_FREE_FIXTURE_CONSENSUS"):
            finalize(self.site,now=self.now)

    def test_missing_cross_publisher_consensus_panel_rejected(self):
        p=self.site/"index.html"
        p.write_text(p.read_text(encoding="utf-8").replace(
            'id="fk-fixture-integrity"','id="not-integrity"'),encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"INVALID_FREE_FIXTURE_CONSENSUS"):
            finalize(self.site,now=self.now)

    def test_production_gate_never_opened(self):
        self.gate["status"]="READY"
        self.write()
        with self.assertRaisesRegex(ValueError,"INVALID_PRODUCTION_QUALIFICATION_GATE"):
            finalize(self.site,now=self.now)


if __name__ == "__main__":
    unittest.main()
