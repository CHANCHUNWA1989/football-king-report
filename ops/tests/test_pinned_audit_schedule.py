"""Static safeguards for the bounded, read-only cohort schedule."""
import unittest
from pathlib import Path


class PinnedAuditScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow=(Path(__file__).resolve().parents[2]/".github/workflows/football-king-readonly-rehearsal.yml").read_text()
        cls.rehearsal,cls.audit=cls.workflow.split("  archived-evidence-audit:",1)

    def test_scheduled_run_is_read_only_and_not_forecast_generation(self):
        self.assertIn("20 10 * * *",self.workflow)
        self.assertIn("github.event_name != 'schedule' &&",self.rehearsal)
        self.assertIn("github.ref == 'refs/heads/main'",self.audit)
        self.assertIn("contents: read",self.audit)
        self.assertIn("actions: read",self.audit)
        self.assertNotIn("contents: write",self.audit)
        scheduled=self.audit.split('if [ "$EVENT_NAME" = schedule ]; then',1)[1].split("fi",1)[0]
        self.assertIn('cp sources/live_germany_latest.json',scheduled)
        self.assertIn("exit 0",scheduled)
        self.assertNotIn("python ops/live_germany.py",scheduled)

    def test_all_expensive_steps_are_gated_by_finite_window(self):
        self.assertIn('"2026-11-29"<=now<="2027-01-04"',self.audit)
        steps=self.audit.split("      - ")[1:]
        self.assertGreaterEqual(len(steps),8)
        for step in steps[1:]:
            self.assertIn("steps.audit_window.outputs.enabled == 'true'",step)
        self.assertIn("scheduled' || 'interactive'",self.workflow)


if __name__=="__main__":
    unittest.main()
