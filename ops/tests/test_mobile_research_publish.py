"""Regression guard for publishing research evidence on iPhone site."""
import unittest
from pathlib import Path


class ResearchSiteWorkflowTests(unittest.TestCase):
    def test_mobile_workflow_publishes_unified_evidence(self):
        root = Path(__file__).resolve().parents[2]
        workflow = (root / ".github/workflows/football-king-iphone.yml").read_text(encoding="utf-8")
        self.assertIn("python ops/unified_research.py --input inputs/shadow_predictions.csv --output app/site/unified_research.json", workflow)
        self.assertIn("assert report['production_recommendations'] == 'DISABLED'", workflow)
        self.assertIn("assert report['status'] == 'HOLD'", workflow)
        self.assertIn("uses: actions/upload-pages-artifact@", workflow)


if __name__ == "__main__":
    unittest.main()
