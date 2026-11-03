"""Prove BSD staging never writes a literal variable path or production main.

The archiver now stages all changed files into ONE fast-forward Git commit
instead of independently writing Contents API files. Verify distinct paths.
"""
import unittest
from pathlib import Path

WORKFLOW = (Path(__file__).resolve().parents[2] /
            ".github/workflows/football-king-bsd-free.yml")


class BSDArchiveTargetTests(unittest.TestCase):
    def test_atomic_git_commit_stages_distinct_history_and_latest_paths(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('history="sources/bsd_history/$folder/$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT.json.gz"', source)
        self.assertIn('git -C "$archive_dir" add -- "$history"', source)
        self.assertIn('git -C "$archive_dir" add -- sources/bsd_status_latest.json', source)
        self.assertIn('git -C "$archive_dir" add -- sources/bsd_market_latest.json', source)
        self.assertIn('if [ "$eligible" = True ]; then', source)
        self.assertIn('git -C "$archive_dir" commit', source)
        self.assertIn('git -C "$archive_dir" push origin "HEAD:refs/heads/$BSD_ARCHIVE_REF"', source)
        self.assertIn('test "$BSD_ARCHIVE_REF" = "archive/bsd-free-research-v1"', source)
        self.assertNotIn('git -C "$archive_dir" add -- "$target"', source)
        self.assertNotIn('refs/heads/main', source)
        self.assertNotIn('--force', source)
        self.assertNotIn('gh api -X PUT', source)


if __name__ == "__main__":
    unittest.main()
