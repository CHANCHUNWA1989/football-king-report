import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_orchestrator import audit

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
            payload["providers"] = [{"provider": "thesportsdb", "status": "PARTIAL_COVERAGE"}]
        target.write_text(json.dumps(payload), encoding="utf-8")

class AgentAuditTests(unittest.TestCase):
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
