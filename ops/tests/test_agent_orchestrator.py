import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_orchestrator import audit
from agent_report import render

NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)

def fixture(root, market_hours=1):
    for path in ("ops/research_recommender.py", "ops/forward_validation.py", "ops/release_guard.py"):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("", encoding="utf-8")
    for path, field, age in (
        ("market/latest.json", "as_of_utc", market_hours),
        ("sources/latest.json", "collected_utc", 1),
    ):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {"status": "RESEARCH_ONLY", field: (NOW - timedelta(hours=age)).isoformat()}
        if path.startswith("market/"):
            payload["leagues"] = [{"league": "epl", "events": 1}]
        else:
            payload["providers"] = [{"provider": "thesportsdb", "status": "PARTIAL_COVERAGE",
                                     "configured": True, "sampled_fixture_count": 1}]
        target.write_text(json.dumps(payload), encoding="utf-8")

class AgentAuditTests(unittest.TestCase):
    def test_agent_audit_runs_after_successful_collectors_only(self):
        workflow = (Path(__file__).resolve().parents[2] /
                    ".github/workflows/football-king-agent-audit.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_run:", workflow)
        self.assertIn("types: [completed]", workflow)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", workflow)
        self.assertIn("Football King private all-market research", workflow)
        self.assertIn("足球王者｜四個免費後備來源獨立採集", workflow)
        self.assertIn("足球王者 V4.1｜免費賠率市場研究及配額保護", workflow)

    def test_mobile_report_escapes_untrusted_diagnostics(self):
        report = {"status": "HOLD", "next_action": "REFRESH_OR_REPAIR_INPUTS",
                  "sources": [{"path": "<script>alert(1)</script>",
                               "status": "HOLD", "reason": "STALE & INVALID"}]}
        page = render(report)
        self.assertIn("REFRESH_OR_REPAIR_INPUTS", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<script>", page)
        self.assertIn("STALE &amp; INVALID", page)
        self.assertIn("自動投注：停用", page)

    def test_mobile_ready_does_not_enable_betting(self):
        page = render({"status": "READY_FOR_MANUAL_REVIEW",
                       "next_action": "MANUAL_REVIEW_ONLY", "sources": []})
        self.assertIn("MANUAL_REVIEW_ONLY", page)
        self.assertIn("正式推薦：停用", page)

    def test_missing_is_hold(self):
        with tempfile.TemporaryDirectory() as d:
            r = audit(Path(d), NOW)
            self.assertEqual(r["status"], "HOLD")
            self.assertFalse(r["automatic_bets"])
            self.assertEqual(r["next_action"], "REFRESH_OR_REPAIR_INPUTS")
            self.assertTrue(r["diagnostics"])

    def test_fresh_sources_are_research_only(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fixture(root)
            r = audit(root, NOW)
            self.assertEqual(r["status"], "HOLD")
            self.assertEqual(r["actions_performed"], [])
            self.assertIn({"component": "evidence/settled.json", "reason": "MISSING"}, r["diagnostics"])
            self.assertEqual(r["six_pillar_progress"]["provider_coverage"]["usable_provider_count"], 1)
            self.assertEqual(r["six_pillar_progress"]["provider_coverage"]["sampled_fixture_total"], 1)
            self.assertIn("可用免費來源：1", render(r))
            self.assertIn("來源抽樣賽事（可能重疊）：1", render(r))
            self.assertEqual(r["next_action"], "REFRESH_OR_REPAIR_INPUTS")
            self.assertEqual(r["production_recommendations"], "DISABLED")

    def test_real_free_provider_partial_is_research_usable_but_still_hold(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fixture(root)
            source = root / "sources/latest.json"
            data = json.loads(source.read_text(encoding="utf-8"))
            # Actual secondary-source snapshots emit PARTIAL, not PARTIAL_COVERAGE.
            data["providers"][0]["status"] = "PARTIAL"
            data["providers"][0]["sampled_fixture_count"] = 10
            data["providers"].append({
                "provider": "api_football", "status": "HOLD",
                "configured": True, "sampled_fixture_count": 0
            })
            source.write_text(json.dumps(data), encoding="utf-8")
            result = audit(root, NOW)
            self.assertEqual(result["sources"][1]["status"], "READY_RESEARCH")
            coverage = result["six_pillar_progress"]["provider_coverage"]
            self.assertEqual(coverage["usable_provider_count"], 1)
            self.assertEqual(coverage["sampled_fixture_total"], 10)
            # Schedule coverage alone is not independent result evidence.
            self.assertEqual(result["status"], "HOLD")
            self.assertFalse(result["automatic_bets"])
            self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_partial_without_real_samples_remains_hold(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fixture(root)
            source = root / "sources/latest.json"
            data = json.loads(source.read_text(encoding="utf-8"))
            data["providers"][0]["status"] = "PARTIAL"
            data["providers"][0]["sampled_fixture_count"] = 0
            source.write_text(json.dumps(data), encoding="utf-8")
            result = audit(root, NOW)
            self.assertEqual(result["sources"][1]["reason"], "EMPTY_SOURCE_COVERAGE")
            self.assertEqual(result["status"], "HOLD")

    def _audit_provider_rows(self, rows, **source_changes):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root)
            path = root / "sources/latest.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["providers"] = rows
            data.update(source_changes)
            path.write_text(json.dumps(data), encoding="utf-8")
            return audit(root, NOW)

    def test_each_accepted_status_counts_only_limited_research_coverage(self):
        for status in ("READY_RESEARCH", "PARTIAL_COVERAGE", "PARTIAL"):
            with self.subTest(status=status):
                result = self._audit_provider_rows([{
                    "provider": "thesportsdb", "status": status,
                    "configured": True, "sampled_fixture_count": 10}])
                self.assertEqual(result["sources"][1]["status"], "READY_RESEARCH")
                self.assertEqual(result["six_pillar_progress"]["provider_coverage"], {
                    "usable_provider_count": 1, "sampled_fixture_total": 10})
                self.assertEqual(result["status"], "HOLD")
                self.assertFalse(result["automatic_bets"])
                self.assertFalse(result["six_pillar_progress"]["all_six_updates_complete"])
                self.assertEqual(result["six_pillar_progress"]["settlement"][
                    "independently_verified_observations"], 0)
                for flag in ("end_to_end_workflow_verified", "pre_match_archive_verified",
                             "post_match_settlement_execution_verified", "model_superiority_verified"):
                    self.assertFalse(result["six_pillar_progress"][flag])
                self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_malformed_status_does_not_erase_valid_partial_in_either_order(self):
        good = {"provider": "thesportsdb", "status": "PARTIAL",
                "configured": True, "sampled_fixture_count": 10}
        for malformed in ([], {}):
            bad = {"provider": "malformed", "status": malformed,
                   "configured": True, "sampled_fixture_count": 999}
            for rows in ([bad, good], [good, bad]):
                with self.subTest(status=malformed, good_first=rows[0] is good):
                    result = self._audit_provider_rows(rows)
                    self.assertEqual(result["sources"][1]["status"], "READY_RESEARCH")
                    self.assertEqual(result["six_pillar_progress"]["provider_coverage"], {
                        "usable_provider_count": 1, "sampled_fixture_total": 10})

    def test_missing_or_invalid_provider_identity_never_inflates_mixed_coverage(self):
        good = {"provider": "thesportsdb", "status": "PARTIAL",
                "configured": True, "sampled_fixture_count": 10}
        for identity in (None, "", "   ", 42, True, [], {}):
            bad = {"provider": identity, "status": "PARTIAL", "configured": True,
                   "sampled_fixture_count": 999}
            if identity is None:
                bad.pop("provider")
            for rows in ([bad, good], [good, bad]):
                with self.subTest(identity=identity, good_first=rows[0] is good):
                    result = self._audit_provider_rows(rows)
                    self.assertEqual(result["sources"][1]["status"], "READY_RESEARCH")
                    self.assertEqual(result["six_pillar_progress"]["provider_coverage"], {
                        "usable_provider_count": 1, "sampled_fixture_total": 10})

    def test_only_invalid_provider_rows_are_not_usable_research(self):
        valid = {"provider": "thesportsdb", "status": "PARTIAL",
                 "configured": True, "sampled_fixture_count": 10}
        invalid = {
            "provider": (None, "", "   ", 42, True, [], {}),
            "configured": (False, None, 1, "true", {}, []),
            "status": ("UNKNOWN", "HOLD", "partial", "", None, False, [], {}),
            "sampled_fixture_count": (0, -1, True, False, 10.0, "10", None, [], {}),
        }
        for field, values in invalid.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    row = dict(valid, **{field: value})
                    result = self._audit_provider_rows([row])
                    self.assertEqual(result["sources"][1]["reason"], "EMPTY_SOURCE_COVERAGE")
                    self.assertEqual(result["six_pillar_progress"]["provider_coverage"], {
                        "usable_provider_count": 0, "sampled_fixture_total": 0})
                    self.assertEqual(result["status"], "HOLD")
                    self.assertFalse(result["automatic_bets"])
            with self.subTest(missing_field=field):
                row = dict(valid)
                row.pop(field)
                result = self._audit_provider_rows([row])
                self.assertEqual(result["sources"][1]["reason"], "EMPTY_SOURCE_COVERAGE")

    def test_non_object_rows_are_ignored_beside_usable_partial(self):
        good = {"provider": "thesportsdb", "status": "PARTIAL",
                "configured": True, "sampled_fixture_count": 10}
        for malformed in (None, False, 42, "provider", []):
            with self.subTest(row=malformed):
                result = self._audit_provider_rows([malformed, good])
                self.assertEqual(result["sources"][1]["status"], "READY_RESEARCH")
                self.assertEqual(result["six_pillar_progress"]["provider_coverage"], {
                    "usable_provider_count": 1, "sampled_fixture_total": 10})

    def test_invalid_provider_collection_format_remains_hold(self):
        for rows in (None, {}, "providers", False):
            with self.subTest(collection=rows):
                result = self._audit_provider_rows(rows)
                self.assertEqual(result["sources"][1]["reason"], "EMPTY_SOURCE_COVERAGE")
                self.assertEqual(result["six_pillar_progress"]["provider_coverage"], {
                    "usable_provider_count": 0, "sampled_fixture_total": 0})
                self.assertEqual(result["status"], "HOLD")

    def test_valid_partial_does_not_bypass_snapshot_time_or_safety_checks(self):
        good = {"provider": "thesportsdb", "status": "PARTIAL",
                "configured": True, "sampled_fixture_count": 10}
        for change, reason in (
            ({"collected_utc": (NOW - timedelta(hours=25)).isoformat()}, "STALE"),
            ({"collected_utc": (NOW + timedelta(minutes=6)).isoformat()}, "FUTURE_TIMESTAMP"),
            ({"collected_utc": NOW.replace(tzinfo=None).isoformat()}, "NAIVE_TIMESTAMP"),
            ({"collected_utc": None}, "MISSING_TIMESTAMP"),
            ({"production_recommendations": "ENABLED"}, "UNSAFE_PRODUCTION_FLAG"),
            ({"status": "HOLD"}, "SOURCE_NOT_READY"),
        ):
            with self.subTest(change=change):
                result = self._audit_provider_rows([good], **change)
                self.assertEqual(result["sources"][1]["reason"], reason)
                self.assertEqual(result["six_pillar_progress"]["provider_coverage"], {
                    "usable_provider_count": 0, "sampled_fixture_total": 0})
                self.assertEqual(result["status"], "HOLD")
                self.assertFalse(result["automatic_bets"])
                self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_fresh_but_empty_market_holds(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fixture(root)
            market = root / "market/latest.json"
            data = json.loads(market.read_text(encoding="utf-8"))
            data["leagues"] = []
            market.write_text(json.dumps(data), encoding="utf-8")
            result = audit(root, NOW)
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(result["sources"][0]["reason"], "EMPTY_MARKET_COVERAGE")

    def test_fresh_but_empty_providers_holds(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fixture(root)
            source = root / "sources/latest.json"
            data = json.loads(source.read_text(encoding="utf-8"))
            data["providers"] = []
            source.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(audit(root, NOW)["status"], "HOLD")

    def test_boolean_event_count_holds(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fixture(root)
            market = root / "market/latest.json"
            data = json.loads(market.read_text(encoding="utf-8"))
            data["leagues"][0]["events"] = True
            market.write_text(json.dumps(data), encoding="utf-8")
            result = audit(root, NOW)
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(result["sources"][0]["reason"], "NO_MARKET_EVENTS")

    def test_missing_league_identity_holds(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fixture(root)
            market = root / "market/latest.json"
            data = json.loads(market.read_text(encoding="utf-8"))
            data["leagues"][0].pop("league")
            market.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(audit(root, NOW)["status"], "HOLD")

    def test_empty_provider_identity_holds(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fixture(root)
            source = root / "sources/latest.json"
            data = json.loads(source.read_text(encoding="utf-8"))
            data["providers"] = [{"status": "PARTIAL_COVERAGE"}]
            source.write_text(json.dumps(data), encoding="utf-8")
            result = audit(root, NOW)
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(result["sources"][1]["reason"], "EMPTY_SOURCE_COVERAGE")

    def test_only_unconfigured_providers_hold(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fixture(root)
            source = root / "sources/latest.json"
            data = json.loads(source.read_text(encoding="utf-8"))
            data["providers"][0]["configured"] = False
            source.write_text(json.dumps(data), encoding="utf-8")
            result = audit(root, NOW)
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(result["sources"][1]["reason"], "EMPTY_SOURCE_COVERAGE")

    def test_zero_observed_fixtures_hold(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fixture(root)
            source = root / "sources/latest.json"
            data = json.loads(source.read_text(encoding="utf-8"))
            data["providers"][0]["sampled_fixture_count"] = 0
            source.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(audit(root, NOW)["status"], "HOLD")

    def test_boolean_fixture_count_holds(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fixture(root)
            source = root / "sources/latest.json"
            data = json.loads(source.read_text(encoding="utf-8"))
            data["providers"][0]["sampled_fixture_count"] = True
            source.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(audit(root, NOW)["status"], "HOLD")

    def test_missing_settlement_never_claims_six_pillars_complete(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fixture(root)
            result = audit(root, NOW)
            progress = result["six_pillar_progress"]
            self.assertFalse(progress["all_six_updates_complete"])
            self.assertEqual(progress["remaining_to_target"], 1000)
            self.assertEqual(progress["settlement"]["status"], "HOLD")
            self.assertIn("evidence/settled.json", render(result))

    def test_valid_unverified_settlement_counts_only_observations(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fixture(root)
            path = root / "evidence/settled.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "schema": "football-king-forward-research-1",
                "checked_utc": NOW.isoformat(),
                "samples": [{"key": "fixture-1", "league": "epl",
                    "kickoff_utc": NOW.isoformat(),
                    "forecast_utc": (NOW - timedelta(hours=2)).isoformat(),
                    "market_utc": (NOW - timedelta(hours=3)).isoformat(),
                    "p": [0.5, 0.3, 0.2], "m": [0.4, 0.3, 0.3], "y": 0,
                    "fixture_result_source_independently_verified": False,
                    "production_recommendations": "DISABLED"}], "n": 1,
                "results_independently_verified": False,
                "profitability_verified": False,
                "production_recommendations": "DISABLED"
            }), encoding="utf-8")
            result = audit(root, NOW)
            self.assertEqual(result["status"], "READY_FOR_MANUAL_REVIEW")
            self.assertEqual(result["six_pillar_progress"]["remaining_to_target"], 999)
            self.assertEqual(result["six_pillar_progress"]["settlement"]["independently_verified_observations"], 0)
            self.assertIn("距離1000場：999", render(result))
            stale_report = audit(root, NOW + timedelta(hours=49))
            self.assertEqual(stale_report["six_pillar_progress"]["settlement"]["status"], "STALE")
            self.assertIn("結算資料狀態：STALE", render(stale_report))
            self.assertEqual(stale_report["status"], "HOLD")
            self.assertEqual(stale_report["next_action"], "REFRESH_OR_REPAIR_INPUTS")
            self.assertIn({"component": "evidence/settled.json", "reason": "SETTLEMENT_OLDER_THAN_48H"}, stale_report["diagnostics"])
            self.assertIn("資料年齡（小時）：49.0", render(stale_report))

    def test_invalid_settlement_rows_not_counted(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fixture(root)
            path = root / "evidence/settled.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "schema": "football-king-forward-research-1",
                "checked_utc": NOW.isoformat(),
                "samples": [{}], "n": 1,
                "results_independently_verified": False,
                "production_recommendations": "DISABLED"
            }), encoding="utf-8")
            progress = audit(root, NOW)["six_pillar_progress"]
            self.assertEqual(progress["settlement"]["status"], "HOLD")
            self.assertEqual(progress["settlement"]["observations"], 0)

    def test_stale_market_holds(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fixture(root, market_hours=30)
            self.assertEqual(audit(root, NOW)["status"], "HOLD")

    def test_future_timestamp_holds(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fixture(root, market_hours=-3)
            self.assertEqual(audit(root, NOW)["status"], "HOLD")

if __name__ == "__main__":
    unittest.main()
