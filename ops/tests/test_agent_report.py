import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_report import render

class AgentReportTests(unittest.TestCase):
    def test_escapes_untrusted_values(self):
        page = render({"status": "<script>alert(1)</script>",
                       "sources": [{"path": "<img src=x>", "status": "HOLD", "reason": "STALE"}]})
        self.assertNotIn("<script>", page)
        self.assertNotIn("<img src=x>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("自動投注：停用", page)

if __name__ == "__main__":
    unittest.main()
