import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
CRITICAL=(
    "football-king-iphone.yml",
    "football-king-ci.yml",
    "football-king-odds.yml",
    "football-king-secondary-sources.yml",
    "football-king-forward-settlement.yml",
    "six-capability-stress.yml",
)

class WorkflowSafetyPolicy(unittest.TestCase):
    def test_critical_actions_pinned(self):
        for name in CRITICAL:
            with self.subTest(name=name):
                body=(ROOT/".github"/"workflows"/name).read_text()
                refs=re.findall(r"uses:\s*(actions/[^\s]+)",body)
                self.assertTrue(refs)
                for ref in refs:
                    self.assertRegex(ref,r"^actions/[a-z-]+@[0-9a-f]{40}$")

    def test_daily_archive_batches_three_files(self):
        body=(ROOT/".github"/"workflows"/"football-king-iphone.yml").read_text()
        self.assertIn("python ops/archive_prepare.py",body)
        self.assertIn("git worktree add --detach",body)
        self.assertIn("push origin HEAD:refs/heads/main",body)
        self.assertNotIn("upload_commit()",body)

if __name__=="__main__":
    unittest.main()
