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
            self.assertEqual(r["status"], "READY_FOR_MANUAL_REVIEW")
            self.assertEqual(r["actions_performed"], [])
            self.assertEqual(r["diagnostics"], [])
            self.assertEqual(r["next_action"], "MANUAL_REVIEW_ONLY")
            self.assertEqual(r["production_recommendations"], "DISABLED")

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
            self.assertEqual(result["six_pillar_progress"]["remaining_to_target"], 999)
            self.assertEqual(result["six_pillar_progress"]["settlement"]["independently_verified_observations"], 0)
            self.assertIn("距離1000場：999", render(result))
            self.assertEqual(audit(root, NOW + timedelta(hours=49))["six_pillar_progress"]["settlement"]["status"], "STALE")

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
