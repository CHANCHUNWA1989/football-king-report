"""Regression checks for provenance, fail-closed, and point-in-time snapshots."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quality_gate import audit, apply
from snapshot import create_snapshot


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 9, 4, 0, tzinfo=timezone.utc)
        self.stamp = self.now.isoformat()
        self.future = (self.now + timedelta(days=1)).isoformat()
        self.report = {
            "checked_utc": self.stamp, "status": "RESEARCH_ONLY",
            "production_recommendations": "DISABLED",
            "fixture_source_records": [{
                "league": "epl", "source": "public", "status": "READY_RESEARCH",
                "captured_utc": self.stamp, "upstream_updated_utc": None,
                "window_matches": 1, "source_url": "https://example.org/fixtures"}],
            "fixtures": {"matches": [{
                "league": "epl", "date": "2026-10-10",
                "home": "Home", "away": "Away",
                "kickoff_utc": self.future, "status": "SCHEDULED",
                "score_ft": None, "source": "public", "event_id": "a"}]}
        }
        self.status = {
            "checked_utc": self.stamp, "status": "RESEARCH_ONLY",
            "production_recommendations": "DISABLED"
        }

    def test_healthy_research_is_not_betting_ready(self):
        out = audit(self.report, self.status, now=self.now)
        self.assertEqual(out["status"], "RESEARCH_ONLY")
        self.assertEqual(out["pre_match_snapshot_eligible"], 1)
        self.assertFalse(out["validated_betting_model"])

    def test_stale_report_fails_closed(self):
        out = audit(self.report, self.status, now=self.now + timedelta(days=3))
        self.assertEqual(out["status"], "HOLD")
        self.assertIn("REPORT_TIMESTAMP_OUTSIDE_ALLOWED_WINDOW", out["critical_errors"])

    def test_duplicate_fixture_fails_closed(self):
        self.report["fixtures"]["matches"] *= 2
        self.assertEqual(audit(self.report, self.status, now=self.now)["status"], "HOLD")

    def test_unknown_kickoff_not_prematch_eligible(self):
        self.report["fixtures"]["matches"][0]["kickoff_utc"] = None
        out = create_snapshot(self.report, self.status)
        self.assertEqual(out["eligible_prematch_events"], 0)
        self.assertFalse(out["observations"][0]["eligible_for_prematch_evaluation"])

    def test_older_or_finished_fixture_excluded(self):
        self.report["fixtures"]["matches"][0]["score_ft"] = [1, 0]
        out = create_snapshot(self.report, self.status)
        self.assertEqual(out["eligible_prematch_events"], 0)
        self.assertNotIn("score_ft", out["observations"][0])

    def test_snapshot_rejects_asof_mismatch(self):
        self.status["checked_utc"] = "2026-10-07T12:00:00+00:00"
        with self.assertRaises(ValueError):
            create_snapshot(self.report, self.status)

    def test_quality_report_written_to_site(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d)
            (dest / "report.json").write_text(json.dumps(self.report), encoding="utf-8")
            (dest / "status.json").write_text(json.dumps(self.status), encoding="utf-8")
            (dest / "index.html").write_text(
                '<div class="status" id="research-banner" data-checked="x">OK</div>'
                '<h2>近期賽程與賽果</h2>正式投注推薦：停用', encoding="utf-8")
            result = apply(dest, now=self.now)
            self.assertEqual(result["status"], "RESEARCH_ONLY")
            self.assertIn('id="quality-audit"', (dest / "index.html").read_text(encoding="utf-8"))
            self.assertTrue((dest / "quality.json").exists())


if __name__ == "__main__":
    unittest.main()
