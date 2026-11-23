"""Fail-first offline continuity tests for isolated weekly Issue notifications."""
import hashlib
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from weekly_digest import digest, to_markdown
from weekly_isolated_archive import BRANCH, PREFIX, ArchiveHold, _git_blob_sha
from weekly_isolated_reader import make_verified_notification

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/football-king-weekly.yml"
NOW = datetime(2026, 11, 6, 10, 22, tzinfo=timezone.utc)
DAY = "2026-11-06"


def report(at=NOW):
    return to_markdown(digest(
        {"n": 0, "samples": [], "production_recommendations": "DISABLED"},
        {"as_of_utc": at.isoformat(), "quota": {"remaining": 150},
         "production_recommendations": "DISABLED"},
        at)).encode("utf-8")


class FakeReadOnlyStore:
    def __init__(self, remote=None, fake_sha=None):
        self.remote = remote
        self.fake_sha = fake_sha
        self.verified = 0
        self.reads = []

    def verify_branch(self):
        self.verified += 1

    def get(self, path):
        self.reads.append(path)
        if self.remote is None:
            return None
        return (self.remote, self.fake_sha or _git_blob_sha(self.remote))


class WeeklyNotificationContinuity(unittest.TestCase):
    def test_verified_report_only_from_pinned_isolated_branch(self):
        raw = report()
        store = FakeReadOnlyStore(raw)
        notice = make_verified_notification(raw, day=DAY, store=store, now=NOW)
        self.assertEqual(store.verified, 1)
        self.assertEqual(store.reads, [PREFIX + DAY + ".md"])
        self.assertTrue(notice["body"].startswith(raw))
        self.assertIn(BRANCH.encode(), notice["body"])
        self.assertIn(hashlib.sha256(raw).hexdigest().encode(), notice["body"])
        self.assertIn(b"HOLD / DISABLED", notice["body"])
        self.assertFalse(notice["approved_for_betting"])
        self.assertEqual(notice["source_ref"], BRANCH)

    def test_missing_modified_or_forged_archive_never_notifies(self):
        raw = report()
        cases = [
            FakeReadOnlyStore(None),
            FakeReadOnlyStore(raw + b"\nmodified\n"),
            FakeReadOnlyStore(raw, fake_sha="e" * 40),
        ]
        for store in cases:
            with self.subTest(store=store.remote), self.assertRaises(ArchiveHold):
                make_verified_notification(raw, day=DAY, store=store, now=NOW)
            self.assertEqual(store.reads, [PREFIX + DAY + ".md"])

    def test_stale_day_or_unauthorized_lookup_is_hold(self):
        with self.assertRaises(ArchiveHold):
            make_verified_notification(report(), day="2026-11-07",
                                       store=FakeReadOnlyStore(report()), now=NOW)
        class Denied(FakeReadOnlyStore):
            def get(self, path):
                raise ArchiveHold("ARCHIVE_GITHUB_API_DENIED_OR_UNAVAILABLE")
        with self.assertRaises(ArchiveHold):
            make_verified_notification(report(), day=DAY,
                                       store=Denied(report()), now=NOW)

    def test_notice_depends_on_verified_archive_and_duplicate_body_check(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("python ops/weekly_isolated_reader.py", workflow)
        self.assertIn('GH_TOKEN: ', workflow)
        self.assertIn('weekly-notification.md', workflow)
        self.assertIn('--body-file "$RUNNER_TEMP/weekly-notification.md"', workflow)
        self.assertNotIn('--body-file "$RUNNER_TEMP/weekly.md"', workflow)
        self.assertIn("cmp -s", workflow)
        self.assertIn("gh issue view", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertNotIn("gh api -X PUT", workflow)


if __name__ == "__main__":
    unittest.main()
