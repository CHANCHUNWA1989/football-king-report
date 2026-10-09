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
                                  ("production_gate.json", self.gate)):
            (self.site / filename).write_text(json.dumps(payload), encoding="utf-8")
        (self.site / "index.html").write_text(
            '<html><body><div class="status" id="research-banner" data-checked="' +
            self.stamp + '">OLD</div><div>正式投注推薦：停用</div>' +
            '<section id="fk-hub"></section><link rel="stylesheet" href="research_hub.css">' +
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

    def test_production_gate_never_opened(self):
        self.gate["status"]="READY"
        self.write()
        with self.assertRaisesRegex(ValueError,"INVALID_PRODUCTION_QUALIFICATION_GATE"):
            finalize(self.site,now=self.now)


if __name__ == "__main__":
    unittest.main()
