"""Test visible mobile research status and HTML escaping."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_mobile_status import publish


class ResearchMobileStatusTests(unittest.TestCase):
    def test_status_visible_and_escaped(self):
        with tempfile.TemporaryDirectory() as d:
            site = Path(d)
            (site / "index.html").write_text("<html><body><main>足球王者</main></body></html>", encoding="utf-8")
            (site / "unified_research.json").write_text(json.dumps({
                "status": "HOLD", "reason": "<script>alert(1)</script>",
                "accuracy_audit": None, "settled_comparable_matches": 0, "has_sealed_input": False
            }), encoding="utf-8")
            publish(site)
            publish(site)
            body = (site / "index.html").read_text(encoding="utf-8")
            self.assertEqual(body.count('id="fk-unified-research"'), 1)
            self.assertIn("unified_research.json", body)
            self.assertIn("封存預測輸入：缺少或未確認", body)
            self.assertIn("&lt;script&gt;", body)
            self.assertNotIn("<script>", body)


if __name__ == "__main__":
    unittest.main()
