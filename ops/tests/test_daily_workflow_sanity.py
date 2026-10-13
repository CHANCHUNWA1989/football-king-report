"""Prevent escaped-newline corruption in scheduled workflow YAML."""
import unittest
from pathlib import Path


class DailyWorkflowSanityTests(unittest.TestCase):
    def test_daily_workflow_structure(self):
        path = Path(__file__).resolve().parents[2] / ".github/workflows/football-king-autonomous-health.yml"
        raw = path.read_text(encoding="utf-8")
        self.assertIn("schedule:", raw)
        self.assertIn("cron:", raw)
        self.assertIn("python ops/unified_research.py", raw)
        self.assertIn("python ops/autonomous_health_guard.py", raw)
        self.assertIn("            unified-research-report.json\n", raw)
        self.assertNotIn("path: |\\n", raw)
        self.assertNotIn("research (fail closed)\\n", raw)


if __name__ == "__main__":
    unittest.main()
