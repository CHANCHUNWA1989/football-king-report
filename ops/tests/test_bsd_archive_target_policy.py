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

    def test_actions_are_pinned_and_main_code_checkouts_do_not_keep_tokens(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        checkout = "11d5960a326750d5838078e36cf38b85af677262"
        expected_actions = {
            "checkout": checkout,
            "setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",
            "upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",
            "download-artifact": "d3f86a106a0bac45b974a628896c90dbdf5c8093",
        }
        for action, digest in expected_actions.items():
            self.assertIn(f"uses: actions/{action}@{digest}", source)
            self.assertNotRegex(source, rf"uses: actions/{action}@v[0-9]+")

        for label in ("Checkout code", "Checkout safe archiver"):
            self.assertIn(
                f"- name: {label}\n"
                f"        uses: actions/checkout@{checkout}\n"
                "        with:\n"
                "          persist-credentials: false",
                source,
            )
        self.assertIn(
            "path: bsd-write-archive\n"
            "          sparse-checkout:", source,
        )
        # The dedicated archive checkout alone retains the token needed
        # for one non-forced push to the archive branch, never to main.
        self.assertIn("          persist-credentials: true", source)
        self.assertIn('push origin "HEAD:refs/heads/$BSD_ARCHIVE_REF"', source)
        self.assertNotIn("refs/heads/main", source)


if __name__ == "__main__":
    unittest.main()
