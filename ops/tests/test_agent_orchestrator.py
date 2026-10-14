import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_orchestrator import audit

class AgentAuditTests(unittest.TestCase):
    def test_fail_closed_on_missing_components(self):
        with tempfile.TemporaryDirectory() as d:
            result = audit(Path(d), datetime(2026, 10, 14, tzinfo=timezone.utc))
            self.assertEqual(result["status"], "HOLD")
            self.assertFalse(result["automatic_bets"])
            self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_read_only_when_components_present(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for path in ("ops/research_recommender.py", "ops/forward_validation.py", "ops/release_guard.py"):
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("", encoding="utf-8")
            result = audit(root)
            self.assertEqual(result["status"], "READY_FOR_MANUAL_REVIEW")
            self.assertEqual(result["actions_performed"], [])
            self.assertFalse(result["automatic_bets"])

if __name__ == "__main__":
    unittest.main()
