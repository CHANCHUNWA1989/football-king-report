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
        self.write()

    def write(self):
        for filename, payload in (("report.json", self.report), ("status.json", self.status),
                                  ("quality.json", self.quality), ("validation.json", self.validation),
                                  ("shadow.json", self.shadow), ("crosscheck.json", self.crosscheck)):
            (self.site / filename).write_text(json.dumps(payload), encoding="utf-8")
        (self.site / "index.html").write_text(
            '<html><body><div class="status" id="research-banner" data-checked="' +
            self.stamp + '">OLD</div><div>正式投注推薦：停用</div>' +
            '<script src="freshness.js" defer></script></body></html>', encoding="utf-8")

    def test_replaces_client_freshness_to_ten_hours(self):
        self.assertEqual(finalize(self.site, now=self.now)["status"], "RESEARCH_ONLY")
        js = (self.site / "freshness.js").read_text()
        self.assertIn("10*60*60*1000", js)
        h = (self.site / "index.html").read_text()
        self.assertIn('id="quality-audit"', h)
        self.assertIn('id="shadow-validation"', h)
        self.assertIn('id="shadow-research-only"', h)
        self.assertIn('id="independent-source-check"', h)
        self.assertIn("RESEARCH_ONLY", h)

    def test_stale_data_visible_hold(self):
        self.stamp = (self.now - timedelta(hours=11)).isoformat()
        self.report["checked_utc"] = self.status["checked_utc"] = self.quality["checked_utc"] = self.stamp
        self.shadow["as_of_utc"] = self.stamp
        self.write()
        self.assertEqual(finalize(self.site, now=self.now)["status"], "HOLD")
        self.assertIn("HOLD：品質或更新時間未通過", (self.site / "index.html").read_text())

    def test_bad_html_without_banner_fails_closed(self):
        (self.site / "index.html").write_text("<html><body>正式投注推薦：停用</body></html>")
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
        (self.site / "index.html").write_text(
            '<div id="research-banner"></div>正式投注推薦：停用<script src="freshness.js"></script>')
        with self.assertRaisesRegex(ValueError, "MISSING_HTML_BODY_END"):
            finalize(self.site, now=self.now)


if __name__ == "__main__":
    unittest.main()
